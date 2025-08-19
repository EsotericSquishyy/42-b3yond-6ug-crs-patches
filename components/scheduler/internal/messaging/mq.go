package messaging

import (
	"context"
	"crs-scheduler/config"
	"errors"
	"math/rand"
	"sync"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

const (
	ConnectionPoolSize = 10
)

type RabbitMQ interface {
	GetChannel() *amqp.Channel
}

type rabbitMQImpl struct {
	logger      *zap.Logger
	rabbitmqUrl string
	context     context.Context
	connections []*MQConnection
	mu          sync.Mutex
}

type MQConnection struct {
	conn      *amqp.Connection
	closeChan chan *amqp.Error
	logger    *zap.Logger

	closed bool
	mu     sync.Mutex
}

type RabbitMQParams struct {
	fx.In

	Config    *config.AppConfig
	Logger    *zap.Logger
	Lifecycle fx.Lifecycle
}

func NewRabbitMQ(p RabbitMQParams) RabbitMQ {
	mqCtx, cancel := context.WithCancel(context.Background())

	svc := &rabbitMQImpl{
		logger:      p.Logger,
		rabbitmqUrl: p.Config.RabbitMQURL,
		context:     mqCtx,
		connections: make([]*MQConnection, 0, ConnectionPoolSize),
		mu:          sync.Mutex{},
	}

	p.Lifecycle.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			svc.logger.Info("Initializing RabbitMQ connection pool", zap.Int("pool_size", ConnectionPoolSize))
			for range ConnectionPoolSize {
				mConn, err := svc.newMQConnection()
				if err != nil {
					svc.logger.Error("Failed to create initial RabbitMQ connection", zap.Error(err))
					return err
				}
				svc.mu.Lock()
				svc.connections = append(svc.connections, mConn)
				svc.mu.Unlock()
			}
			return nil
		},
		OnStop: func(ctx context.Context) error {
			cancel()
			return nil
		},
	})
	return svc
}

func (r *rabbitMQImpl) getActiveConnection() (*MQConnection, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	candidates := make([]*MQConnection, 0)

	for i := range r.connections {
		r.connections[i].mu.Lock()
		if !r.connections[i].closed {
			candidates = append(candidates, r.connections[i])
		}
		r.connections[i].mu.Unlock()
	}

	// Replenish pool if the number of active connections is below the pool size
	if len(candidates) < ConnectionPoolSize {
		needed := ConnectionPoolSize - len(candidates)
		r.logger.Info("Refilling RabbitMQ connection pool", zap.Int("needed", needed))
		for range needed {
			mConn, err := r.newMQConnection()
			if err != nil {
				r.logger.Error("Failed to create new RabbitMQ connection", zap.Error(err))
				continue
			}
			r.connections = append(r.connections, mConn)
			candidates = append(candidates, mConn)
		}
	}

	if len(candidates) == 0 {
		r.logger.Error("No active RabbitMQ connections available")
		return nil, errors.New("no active RabbitMQ connections")
	}

	// Return a random active connection
	randomIndex := rand.Intn(len(candidates))
	return candidates[randomIndex], nil
}

func (r *rabbitMQImpl) newMQConnection() (*MQConnection, error) {
	conn, err := amqp.Dial(r.rabbitmqUrl)
	if err != nil {
		return nil, err
	}

	mConn := MQConnection{
		conn,
		make(chan *amqp.Error),
		r.logger,
		false,
		sync.Mutex{},
	}

	go mConn.monitor(r.context)

	return &mConn, nil
}

// monitor the connection. This function is blocking and is intended to be called in a go routine.
func (c *MQConnection) monitor(ctx context.Context) {
	c.conn.NotifyClose(c.closeChan)

	select {
	case err := <-c.closeChan:
		c.logger.Error("RabbitMQ connection closed", zap.Error(err))
		c.mu.Lock()
		c.closed = true
		c.mu.Unlock()
	case <-ctx.Done():
	}

	c.conn.Close()
}

// GetChannel will spin until it can get a channel from an active connection.
// If it cannot get a channel from anywhere for 5 minutes, it will raise a fatal error.
func (r *rabbitMQImpl) GetChannel() *amqp.Channel {
	ctx, cancel := context.WithTimeout(r.context, 5*time.Minute)
	defer cancel()

	avaiableChannel := make(chan *amqp.Channel, 1)
	go func() {
		// Spin until we can get a channel from an active connection
		for {
			select {
			case <-ctx.Done():
				return
			default:
				conn, err := r.getActiveConnection()
				if err != nil {
					r.logger.Error("Failed to get RabbitMQ channel", zap.Error(err))
					continue
				}
				ch, err := conn.conn.Channel()
				if err != nil {
					r.logger.Error("Failed to create RabbitMQ channel", zap.Error(err))
					continue
				}
				avaiableChannel <- ch
				return
			}
		}
	}()

	select {
	case ch := <-avaiableChannel:
		return ch
	case <-ctx.Done():
		r.logger.Fatal("Failed to get RabbitMQ channel within timeout", zap.Error(ctx.Err()))
		return nil
	}
}

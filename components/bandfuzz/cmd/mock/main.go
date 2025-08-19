package main

// mock the scheduler

import (
	"b3fuzz/config"
	"b3fuzz/pkg/database"
	"b3fuzz/pkg/logger"
	"b3fuzz/pkg/mq"
	"b3fuzz/pkg/telemetry"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/google/uuid"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

const (
	QueueName       = "artifact_queue"
	MetadataKey     = "global:task_metadata:%s"
	TaskTraceCtxKey = "global:trace_context:%s"
)

// TaskConfig represents the configuration received from the message queue
type TaskConfig struct {
	TaskID         string   `json:"task_id"`
	TaskType       string   `json:"task_type"`
	ProjectName    string   `json:"project_name"`
	Focus          string   `json:"focus"`
	Repo           []string `json:"repo"`            // Repository paths
	FuzzingTooling string   `json:"fuzzing_tooling"` // Path to fuzzing tools
	Diff           string   `json:"diff,omitempty"`  // Optional diff URL for delta tasks
	Metadata       string   `json:"metadata"`        // Metadata for the task
}

// FuzzTaskDetails contains paths and information about a downloaded fuzzing task
type FuzzTaskDetails struct {
	TaskID          string
	FuzzToolingPath string // path to the fuzz tooling (oss-fuzz) dir
	RepoPath        string // path to the focus repo dir; patch should be already applied in this dir
	ProjectName     string // name of the project
}

type mockApp struct {
	rabbitMQ     mq.RabbitMQ
	redisClient  *redis.Client
	logger       *zap.Logger
	traceFactory *telemetry.TracerFactory
	shutdowner   fx.Shutdowner
}

type mockParams struct {
	fx.In
	RabbitMQ     mq.RabbitMQ
	RedisClient  *redis.Client
	Logger       *zap.Logger
	TraceFactory *telemetry.TracerFactory
	Shutdowner   fx.Shutdowner
}

func newMockApp(p mockParams) *mockApp {
	return &mockApp{
		rabbitMQ:     p.RabbitMQ,
		redisClient:  p.RedisClient,
		logger:       p.Logger,
		traceFactory: p.TraceFactory,
		shutdowner:   p.Shutdowner,
	}
}

func (m *mockApp) sendMockTask() error {
	channel := m.rabbitMQ.GetChannel()
	defer channel.Close()
	if channel == nil {
		return fmt.Errorf("failed to get RabbitMQ channel")
	}

	// Declare the queue
	q, err := channel.QueueDeclare(
		QueueName,
		true,  // durable
		false, // delete when unused
		false, // exclusive
		false, // no-wait
		nil,   // arguments
	)
	if err != nil {
		return fmt.Errorf("failed to declare queue: %w", err)
	}

	// get current directory
	dir := "/crs"

	// Create a mock task message

	taskId := uuid.New().String()
	taskKey := fmt.Sprintf("global:task_status:%s", taskId)
	m.redisClient.Set(context.Background(), taskKey, "processing", 0)
	seedKey := fmt.Sprintf("cmin:%s:%s", taskId, "decompress_fuzzer")
	m.redisClient.Set(context.Background(), seedKey, "/crs/fake_seeds.tar.gz", 0)

	metadataKey := fmt.Sprintf(MetadataKey, taskId)
	metadata := struct {
		RoundId     string `json:"round_id"`
		ProjectName string `json:"project_name"`
		TaskId      string `json:"task_id"`
	}{
		"pre-round3-unit-test",
		"c-blosc2",
		taskId,
	}
	metadataJson, _ := json.Marshal(metadata)
	m.redisClient.Set(context.Background(), metadataKey, metadataJson, 0)

	tracer := m.traceFactory.NewTracer(context.Background(), taskId)
	tracer.Start()
	defer tracer.End()
	taskTraceCtxKey := fmt.Sprintf(TaskTraceCtxKey, taskId)
	m.redisClient.Set(context.Background(), taskTraceCtxKey, tracer.Export(), 0)

	task := TaskConfig{
		TaskID:         taskId,
		TaskType:       "full",
		ProjectName:    "c-blosc2",
		Focus:          "c-blosc2",
		Repo:           []string{filepath.Join(dir, "tests", "repo.tar.gz")},
		FuzzingTooling: filepath.Join(dir, "tests", "fuzz-tooling.tar.gz"),
	}

	// Marshal the task to JSON
	body, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("failed to marshal task: %w", err)
	}

	// Publish the message
	ctx := context.Background()
	err = channel.PublishWithContext(ctx,
		"",     // exchange
		q.Name, // routing key
		false,  // mandatory
		false,  // immediate
		amqp.Publishing{
			ContentType: "application/json",
			Body:        body,
		},
	)
	if err != nil {
		return fmt.Errorf("failed to publish message: %w", err)
	}

	m.logger.Info("Successfully sent mock task",
		zap.String("task_id", task.TaskID),
		zap.String("queue", q.Name))

	m.shutdowner.Shutdown()

	return nil
}

func NewAppContext(lc fx.Lifecycle) context.Context {
	ctx, cancel := context.WithCancel(context.Background())
	lc.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			return nil
		},
		OnStop: func(ctx context.Context) error {
			cancel()
			return nil
		},
	})
	return ctx
}

func main() {
	// Parse command line flags
	help := flag.Bool("help", false, "Show help message")
	flag.Parse()

	if *help {
		fmt.Println("Usage: mock [options]")
		fmt.Println("\nOptions:")
		flag.PrintDefaults()
		os.Exit(0)
	}

	app := fx.New(
		fx.Provide(
			config.LoadConfig,
			telemetry.NewTelemetry,
			logger.NewLogger,
			telemetry.NewTracerFactory,
			mq.NewRabbitMQ,
			database.NewRedisClient,
			NewAppContext,
			newMockApp,
		),
		fx.Invoke(func(mock *mockApp) error {
			return mock.sendMockTask()
		}),
	)

	app.Run()
}

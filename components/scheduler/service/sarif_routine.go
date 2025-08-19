package service

import (
	"bytes"
	"context"
	"crs-scheduler/internal/messaging"
	"crs-scheduler/internal/scheduler"
	"crs-scheduler/repository"
	"encoding/json"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

const (
	ForwardedSarifsKey = "scheduler:forwarded_sarifs"
)

type SarifRoutineParams struct {
	fx.In

	SarifRepo   repository.SarifRepository
	TaskService TaskService
	TaskRepo    repository.TaskRepository
	RabbitMQ    messaging.RabbitMQ
	RedisClient *redis.Client
	Logger      *zap.Logger
}

type SarifRoutine struct {
	sarifRepo   repository.SarifRepository
	taskService TaskService
	rabbitMQ    messaging.RabbitMQ
	redisClient *redis.Client
	logger      *zap.Logger
}

func NewSarifRoutine(params SarifRoutineParams) scheduler.ScheduleRoutine {
	return &SarifRoutine{
		sarifRepo:   params.SarifRepo,
		taskService: params.TaskService,
		rabbitMQ:    params.RabbitMQ,
		redisClient: params.RedisClient,
		logger:      params.Logger,
	}
}

func (r *SarifRoutine) Run() error {
	// Get all sarifs with processing status
	sarifs, err := r.sarifRepo.GetNewSarif()
	if err != nil {
		r.logger.Error("failed to get new sarifs", zap.Error(err))
		return err
	}

	for _, sarif := range sarifs {
		// Check if this SARIF has already been forwarded
		isForwarded, err := r.redisClient.SIsMember(
			context.Background(),
			ForwardedSarifsKey,
			sarif.ID,
		).Result()
		if err != nil {
			r.logger.Error("failed to check forwarded status", zap.Error(err))
			continue
		}

		if isForwarded {
			continue
		}

		task_queue_element, err := r.taskService.GetTaskQueueElement(sarif.TaskID)
		if err != nil {
			r.logger.Error("failed to get task queue element", zap.Error(err))
			continue
		}

		// append sarif to task_queue_element
		task_queue_element["sarif_id"] = sarif.ID
		task_queue_element["sarif_report"] = sarif.Sarif

		// Encode the task queue element
		var buffer bytes.Buffer
		encoder := json.NewEncoder(&buffer)
		encoder.SetEscapeHTML(false)
		if err := encoder.Encode(task_queue_element); err != nil {
			r.logger.Error("Failed to encode task queue element",
				zap.String("task_id", sarif.TaskID),
				zap.Error(err))
			continue
		}

		// Publish to the sarif queue
		ch := r.rabbitMQ.GetChannel()
		defer ch.Close()

		err = ch.Publish(
			messaging.DirectExchange, // exchange
			messaging.SarifQueue,     // routing key
			false,                    // mandatory
			false,                    // immediate
			amqp.Publishing{
				ContentType: "application/json",
				Body:        buffer.Bytes(),
			},
		)
		if err != nil {
			r.logger.Error("Failed to publish to sarif queue",
				zap.String("task_id", sarif.TaskID),
				zap.Error(err))
			continue
		}

		// After successful publish, mark the SARIF as forwarded in Redis
		err = r.redisClient.SAdd(
			context.Background(),
			ForwardedSarifsKey,
			sarif.ID,
		).Err()
		if err != nil {
			r.logger.Error("Failed to mark sarif as forwarded",
				zap.String("sarif_id", sarif.ID),
				zap.Error(err))
			continue
		}

		r.logger.Info("Successfully published sarif to queue",
			zap.String("task_id", sarif.TaskID),
			zap.String("sarif_id", sarif.ID))
	}

	return nil
}

func (r *SarifRoutine) Cancel() {
}

func (r *SarifRoutine) Name() string {
	return "sarif_routine"
}

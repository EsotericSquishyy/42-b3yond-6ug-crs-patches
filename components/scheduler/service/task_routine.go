package service

import (
	"bytes"
	"context"
	"crs-scheduler/internal/messaging"
	"crs-scheduler/internal/scheduler"
	"crs-scheduler/internal/telemetry"
	"crs-scheduler/models"
	"encoding/json"
	"fmt"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/codes"
	"go.uber.org/zap"
)

const (
	GlobalTaskStatusKey = "global:task_status"
	TaskTraceCtxKey     = "global:trace_context:%s"
)

type TaskRoutine struct {
	taskService   TaskService
	rabbitMQ      messaging.RabbitMQ
	redisClient   *redis.Client
	logger        *zap.Logger
	tracerFactory *telemetry.TracerFactory
}

func NewTaskRoutine(s TaskService, rabbitMQ messaging.RabbitMQ, redisClient *redis.Client, logger *zap.Logger, tracerFactory *telemetry.TracerFactory) scheduler.ScheduleRoutine {
	return &TaskRoutine{
		taskService:   s,
		rabbitMQ:      rabbitMQ,
		redisClient:   redisClient,
		logger:        logger,
		tracerFactory: tracerFactory,
	}
}

func (r *TaskRoutine) Run() error {
	tasks, err := r.taskService.GetPendingTasks()
	if err != nil {
		return err
	}

	for _, task := range tasks {
		if err := r.onTaskReceived(&task); err != nil {
			r.logger.Error("Failed to process task",
				zap.String("task_id", task.ID),
				zap.Error(err),
			)
			continue // Skip to the next task if processing fails
		}
	}

	return nil
}

func (r *TaskRoutine) Cancel() {
}

func (r *TaskRoutine) Name() string {
	return "task_routine"
}

func (r *TaskRoutine) onTaskReceived(task *models.Task) error {
	span := fmt.Sprintf("BugBuster:Processing:%s", task.ID)
	tracer := r.tracerFactory.NewTracer(context.Background(), span)
	tracer.Start()
	defer tracer.End()

	err := r.processTask(task)
	if err != nil {
		r.logger.Error("Failed to process task", zap.String("task_id", task.ID), zap.Error(err))
		tracer.SetStatus(codes.Error, "Failed to process task")
		return err
	}
	// set task status as "processing" in redis
	if err := r.setRedisTaskStatus(task.ID); err != nil {
		r.logger.Error("Failed to set task status in redis", zap.String("task_id", task.ID), zap.Error(err))
		tracer.SetStatus(codes.Error, "Failed to process task")
		return err
	}
	// export the span
	tracingPayload := tracer.Export()
	if err := r.setRedisTaskTracingContext(task.ID, tracingPayload); err != nil {
		r.logger.Error("Failed to set task tracing context in redis",
			zap.String("task_id", task.ID),
			zap.Error(err),
		)
		tracer.SetStatus(codes.Error, "Failed to set task tracing context")
		return err
	}

	return nil
}

func (r *TaskRoutine) publishTaskToQueue(taskID string, rabbitMQ messaging.RabbitMQ) error {
	taskData, err := r.taskService.GetTaskQueueElement(taskID)
	if err != nil {
		return err
	}

	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	err = encoder.Encode(taskData)
	if err != nil {
		return err
	}

	ch := rabbitMQ.GetChannel()
	defer ch.Close()

	err = ch.Publish(
		messaging.TaskBroadcastExchange, // exchange
		"",                              // routing key
		false,                           // mandatory
		false,                           // immediate
		amqp.Publishing{
			ContentType: "application/json",
			Body:        buffer.Bytes(),
		},
	)
	if err != nil {
		return err
	}

	// Save broadcasted task to Redis
	if err := r.taskService.SaveBroadcastedTask(taskID); err != nil {
		r.logger.Error("Failed to save broadcasted task to Redis",
			zap.String("task_id", taskID),
			zap.Error(err))
		return err
	}

	return nil
}

func (r *TaskRoutine) processTask(task *models.Task) error {
	if time.Unix(task.Deadline, 0).Before(time.Now()) {
		r.logger.Warn("Task has passed its deadline, skipping",
			zap.String("task_id", task.ID),
		)
		return nil
	}

	// Check failure count
	failureCount, err := r.taskService.GetFailureCount(task.ID)
	if err != nil {
		r.logger.Error("Failed to get failure count",
			zap.String("task_id", task.ID),
			zap.Error(err))
		return err
	}

	if failureCount >= 3 {
		r.logger.Warn("Task has failed too many times, marking as error",
			zap.String("task_id", task.ID),
			zap.Int("failure_count", failureCount),
		)
		if err := r.taskService.MarkTaskAsError(task.ID); err != nil {
			r.logger.Error("Failed to mark task as error",
				zap.String("task_id", task.ID),
				zap.Error(err),
			)
			return err
		}
		// Clean up the failure count
		if err := r.taskService.ResetFailureCount(task.ID); err != nil {
			r.logger.Error("Failed to reset failure count",
				zap.String("task_id", task.ID),
				zap.Error(err))
		}
		return nil
	}

	// start the task scheduler span

	err = r.taskService.DownloadSources(task.ID)
	if err != nil {
		r.logger.Error("Failed to get task sources",
			zap.String("task_id", task.ID),
			zap.Error(err),
		)
		r.incrementFailureCount(task.ID)
		return err
	}

	// set task metadata
	if err := r.taskService.SetTaskMetadata(task.ID, task.Metadata); err != nil {
		r.logger.Error("Failed to set task metadata",
			zap.String("task_id", task.ID),
			zap.Error(err),
		)
	}

	if err := r.publishTaskToQueue(task.ID, r.rabbitMQ); err != nil {
		r.logger.Error("Failed to publish task to queue",
			zap.String("task_id", task.ID),
			zap.Error(err),
		)
		r.incrementFailureCount(task.ID)
		return err
	}

	if err := r.taskService.MarkTaskAsProcessing(task.ID); err != nil {
		r.logger.Error("Failed to mark task as processing",
			zap.String("task_id", task.ID),
			zap.Error(err),
		)
		r.incrementFailureCount(task.ID)
		return err
	}

	// Success - remove any failure count
	if err := r.taskService.ResetFailureCount(task.ID); err != nil {
		r.logger.Error("Failed to reset failure count",
			zap.String("task_id", task.ID),
			zap.Error(err))
	}

	r.logger.Info("Successfully processed task",
		zap.String("task_id", task.ID),
	)

	return nil
}

func (r *TaskRoutine) incrementFailureCount(taskID string) {
	count, err := r.taskService.IncrementFailureCount(taskID)
	if err != nil {
		r.logger.Error("Failed to increment failure count",
			zap.String("task_id", taskID),
			zap.Error(err))
	} else {
		r.logger.Debug("Incremented failure count",
			zap.String("task_id", taskID),
			zap.Int("count", count))
	}
}

// set task status as "processing" in redis
func (r *TaskRoutine) setRedisTaskStatus(taskID string) error {
	err := r.redisClient.Set(
		context.Background(),
		GlobalTaskStatusKey+":"+taskID, // e.g., global:task_status:<task_id>
		"processing",
		0,
	).Err()
	if err != nil {
		r.logger.Error("Failed to set task status in redis",
			zap.String("task_id", taskID),
			zap.Error(err),
		)
		return err
	}
	return nil
}

func (r *TaskRoutine) setRedisTaskTracingContext(taskID, tracingPayload string) error {
	return r.redisClient.Set(
		context.Background(),
		fmt.Sprintf(TaskTraceCtxKey, taskID), // e.g., global:trace_context:<task_id>
		tracingPayload,
		0,
	).Err()
}

package service

import (
	"context"
	"crs-scheduler/internal/scheduler"
	"time"

	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"
)

type CancelRoutine struct {
	taskService TaskService
	redisClient *redis.Client
	logger      *zap.Logger
}

func NewCancelRoutine(s TaskService, redisClient *redis.Client, logger *zap.Logger) scheduler.ScheduleRoutine {
	return &CancelRoutine{
		taskService: s,
		redisClient: redisClient,
		logger:      logger,
	}
}

func (r *CancelRoutine) Run() error {
	// Get all broadcasted tasks
	tasks, err := r.taskService.GetBroadcastedTasks()
	if err != nil {
		r.logger.Error("Failed to get broadcasted tasks", zap.Error(err))
		return err
	}

	now := time.Now()

	for _, taskID := range tasks {
		logger := r.logger.With(zap.String("task_id", taskID))

		task, err := r.taskService.GetTask(taskID)
		if err != nil {
			logger.Error("Failed to get task", zap.Error(err))
			continue
		}

		// Check if task is canceled
		if task.Status == "canceled" {
			r.logger.Info("Task canceled", zap.String("task_id", taskID))
			if err := r.setCancelStatus(taskID); err != nil {
				logger.Error("Failed to set cancel status", zap.Error(err))
				continue
			}
			// Remove from broadcasted tasks
			if err := r.taskService.RemoveBroadcastedTask(taskID); err != nil {
				logger.Error("Failed to remove broadcasted task", zap.Error(err))
			}
		}

		// Check if task has passed deadline
		if time.UnixMilli(task.Deadline).Before(now) {
			r.logger.Info("Task passed deadline", zap.String("task_id", taskID))
			if err := r.setCancelStatus(taskID); err != nil {
				logger.Error("Failed to set cancel status", zap.Error(err))
				continue
			}

			// Mark as succeeded
			if err := r.taskService.MarkTaskAsSucceeded(taskID); err != nil {
				logger.Error("Failed to mark task as succeeded", zap.Error(err))
			}

			// Remove from broadcasted tasks
			if err := r.taskService.RemoveBroadcastedTask(taskID); err != nil {
				logger.Error("Failed to remove broadcasted task", zap.Error(err))
			}
		}
	}

	return nil
}

func (r *CancelRoutine) setCancelStatus(taskID string) error {
	err := r.redisClient.Set(
		context.Background(),
		GlobalTaskStatusKey+":"+taskID, // e.g., global:task_status:<task_id>
		"canceled",
		0,
	).Err()
	if err != nil {
		r.logger.Error("Failed to set cancel status", zap.String("task_id", taskID), zap.Error(err))
		return err
	}
	return nil
}

func (r *CancelRoutine) Cancel() {
}

func (r *CancelRoutine) Name() string {
	return "cancel_routine"
}

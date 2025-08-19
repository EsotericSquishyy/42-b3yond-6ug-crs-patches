package api

import (
	"context"
	"crs-scheduler/repository"
	"fmt"

	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"
)

const (
	ArtifactHarnessRedisKey = "artifacts:%s:harnesses" // artifacts:<task_id>:harnesses --> [ harness1, harness2, ... ]
)

type HarnessResponse struct {
	Count     int                 `json:"count"`
	Harnesses map[string][]string `json:"harnesses"`
}

type HarnessService struct {
	redisClient *redis.Client
	taskRepo    repository.TaskRepository
	logger      *zap.Logger
}

func NewHarnessService(redisClient *redis.Client, taskRepo repository.TaskRepository, logger *zap.Logger) *HarnessService {
	return &HarnessService{
		redisClient,
		taskRepo,
		logger,
	}
}

func (h *HarnessService) GetHarnessData() (*HarnessResponse, error) {
	tasks, err := h.taskRepo.GetProcessingTasks()
	if err != nil {
		return nil, err
	}

	count := 0
	harnesses := make(map[string][]string)
	for _, task := range tasks {
		artifactHarnessKey := fmt.Sprintf(ArtifactHarnessRedisKey, task.ID)
		harnessNames, err := h.redisClient.SMembers(context.Background(), artifactHarnessKey).Result()
		if err != nil {
			h.logger.Warn("failed to get harnesses info, estimate 5 harnesses", zap.String("task_id", task.ID), zap.Error(err))
			count += 5 // estimate a project may have 5 harnesses
			continue
		}
		count += min(len(harnessNames), 1)
		harnesses[task.ID] = harnessNames
	}

	h.logger.Info("get harnesses count", zap.Int("count", count))

	return &HarnessResponse{
		Count:     count,
		Harnesses: harnesses,
	}, nil
}

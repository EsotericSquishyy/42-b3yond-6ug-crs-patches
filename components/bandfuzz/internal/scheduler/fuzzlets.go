package scheduler

import (
	"b3fuzz/internal/types"
	"context"
	"encoding/json"
	"fmt"

	"go.uber.org/zap"
)

const (
	FuzzLetsKey       = "b3fuzz:fuzzlets"
	TaskStatusKeyTmpl = "global:task_status:%s" // global:task_status:<task_id> --> processing | canceled
)

// grab new fuzzlets from redis, and check task status
func (s *Scheduler) getFuzzlets(ctx context.Context) ([]*types.Fuzzlet, error) {
	s.logger.Debug("getting fuzzlets from redis")
	fuzzletJSONs, err := s.redisClient.SMembers(ctx, FuzzLetsKey).Result()
	if err != nil {
		return nil, err
	}

	fuzzlets := make([]*types.Fuzzlet, 0, len(fuzzletJSONs))

	for _, fuzzletJSON := range fuzzletJSONs {
		fuzzlet := &types.Fuzzlet{}
		if err := json.Unmarshal([]byte(fuzzletJSON), &fuzzlet); err != nil {
			return nil, err
		}

		logger := s.logger.With(zap.String("task_id", fuzzlet.TaskId))

		taskStatusKey := fmt.Sprintf(TaskStatusKeyTmpl, fuzzlet.TaskId)
		status, err := s.redisClient.Get(ctx, taskStatusKey).Result()
		// skip if task is not in status list
		if status != "processing" {

			// remove fuzzlet from redis (only when status is "canceled")
			if status == "canceled" {
				if err := s.redisClient.SRem(ctx, FuzzLetsKey, fuzzletJSON).Err(); err != nil {
					logger.Error("failed to remove fuzzlet from redis", zap.Error(err))
				}
			} else {
				logger.Error("failed to get task status, skipping", zap.Error(err))
			}

			continue
		}

		fuzzlets = append(fuzzlets, fuzzlet)
	}
	s.logger.Info("got fuzzlets from redis", zap.Int("count", len(fuzzlets)))
	return fuzzlets, nil
}

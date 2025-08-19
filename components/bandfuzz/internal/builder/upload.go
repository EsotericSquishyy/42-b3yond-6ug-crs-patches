package builder

import (
	"b3fuzz/internal/scheduler"
	"b3fuzz/internal/types"
	"b3fuzz/internal/utils"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"go.uber.org/zap"
)

const (
	ArtifactRedisKey           = "artifacts:%s:%s:%s:%s:after" // artifacts:<task_id>:<harness_name>:<sanitizer>:<fuzz_engine>:after
	ArtifactHarnessRedisKey    = "artifacts:%s:harnesses"      // artifacts:<task_id>:harnesses --> [ harness1, harness2, ... ]
	DictRedisKey               = "artifacts:%s:%s:dicts"       // artifacts:<task_id>:<harness_name>:dicts
	FuzzingArtifactStoragePath = "/crs/b3fuzz/artifacts/"
)

// upload the artifacts to /crs folder
// returns the path to the uploaded artifact
func (b *TaskBuilder) upload(taskId string, harness string, sanitizer string, engine string, artifactPath string) (string, error) {
	artifactFolder := filepath.Join(FuzzingArtifactStoragePath, taskId, harness, sanitizer, engine)
	if err := os.MkdirAll(artifactFolder, 0755); err != nil {
		b.logger.Error("Failed to create artifact folder", zap.String("path", artifactFolder), zap.Error(err))
		return "", fmt.Errorf("failed to create artifact folder: %w", err)
	}

	uploadPath := filepath.Join(artifactFolder, filepath.Base(artifactPath))
	if err := utils.CopyFile(artifactPath, uploadPath); err != nil {
		b.logger.Error("Failed to copy artifact file", zap.String("src", artifactPath), zap.String("dst", uploadPath), zap.Error(err))
		return "", fmt.Errorf("failed to copy artifact file: %w", err)
	}

	return uploadPath, nil
}

// store the artifact path in Redis
func (b *TaskBuilder) record(ctx context.Context, taskId string, harness string, sanitizer string, engine string, artifactPath string) error {
	// artifacts:<task_id>:<harness_name>:<sanitizer>:<fuzz_engine>:after
	key := fmt.Sprintf(ArtifactRedisKey, taskId, harness, sanitizer, engine)
	if err := b.redisClient.Set(ctx, key, artifactPath, 0).Err(); err != nil {
		b.logger.Error("Failed to set artifact path in Redis", zap.String("key", key), zap.Error(err))
		return fmt.Errorf("failed to set artifact path in Redis: %w", err)
	}
	b.logger.Info("Artifact path set in Redis", zap.String("key", key), zap.String("path", artifactPath))
	return nil
}

// create a new fuzzlet in Redis
func (b *TaskBuilder) addFuzzlet(ctx context.Context, taskId string, harness string, sanitizer string, engine string, artifactPath string) error {
	fuzzlet := types.Fuzzlet{
		TaskId:       taskId,
		Harness:      harness,
		Sanitizer:    sanitizer,
		FuzzEngine:   engine,
		ArtifactPath: artifactPath,
	}

	fuzzletJSON, err := json.Marshal(fuzzlet)
	if err != nil {
		b.logger.Error("Failed to marshal fuzzlet", zap.Error(err))
		return errors.New("failed to marshal fuzzlet")
	}

	b.redisClient.SAdd(ctx, scheduler.FuzzLetsKey, fuzzletJSON)

	return nil
}

func (b *TaskBuilder) updateHarnessList(ctx context.Context, harnesses []string, taskId string) error {
	for _, harness := range harnesses {
		// artifacts:<task_id>:harnesses --> { harness1, harness2, ... }
		key := fmt.Sprintf(ArtifactHarnessRedisKey, taskId)
		if err := b.redisClient.SAdd(ctx, key, harness).Err(); err != nil {
			b.logger.Error("Failed to add harness to Redis", zap.String("key", key), zap.String("harness", harness), zap.Error(err))
			return fmt.Errorf("failed to add harness to Redis: %w", err)
		}
	}
	return nil
}

// upload the artifacts to /crs folder, and sync with Redis
func (b *TaskBuilder) uploadArtifact(ctx context.Context, harness, taskId, sanitizer, engine, artifactPath string) (string, error) {
	uploadPath, err := b.upload(taskId, harness, sanitizer, engine, artifactPath)
	if err != nil {
		b.logger.Error("Failed to upload artifact", zap.String("harness", harness), zap.Error(err))
	} else {
		b.record(ctx, taskId, harness, sanitizer, engine, uploadPath)
	}

	b.logger.Info("Finish uploading artifact and synced with Redis",
		zap.String("taskID", taskId),
		zap.String("harness", harness),
		zap.String("sanitizer", sanitizer),
		zap.String("engine", engine))

	return uploadPath, nil
}

// upload the dict to /crs folder, and sync with Redis
func (b *TaskBuilder) uploadDict(ctx context.Context, harness, taskId, dictPath string) (string, error) {
	uploadPath, err := b.upload(taskId, harness, "dict", "default", dictPath)
	if err != nil {
		b.logger.Error("Failed to upload dict", zap.String("harness", harness), zap.Error(err))
	} else {
		key := fmt.Sprintf(DictRedisKey, taskId, harness)
		if err := b.redisClient.SAdd(ctx, key, uploadPath).Err(); err != nil {
			b.logger.Error("Failed to add dict path to Redis", zap.String("key", key),
				zap.String("path", uploadPath), zap.Error(err))
			return "", fmt.Errorf("failed to add dict path to Redis: %w", err)
		}
	}

	b.logger.Info("Finish uploading dict and synced with Redis",
		zap.String("taskID", taskId),
		zap.String("harness", harness),
		zap.String("dictPath", uploadPath))
	return uploadPath, nil
}

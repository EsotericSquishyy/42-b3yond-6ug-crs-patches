package dict

import (
	"context"
	"fmt"
	"os"
	"strings"

	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

const DictRedisKey = "artifacts:%s:%s:dicts" // artifacts:<task_id>:<harness_name>:dicts

type DictGrabber struct {
	logger      *zap.Logger
	redisClient *redis.Client
}

type DictGrabberParams struct {
	fx.In

	Logger      *zap.Logger
	RedisClient *redis.Client
}

func NewDictGrabber(params DictGrabberParams) *DictGrabber {
	return &DictGrabber{
		params.Logger,
		params.RedisClient,
	}
}

// GrabDict merges dictionary files for a given task and harness.
//
// It retrieves the set of dictionary file paths from Redis using the provided
// taskId and harness, reads and merges their contents, deduplicates lines
// (ignoring empty lines and comments), and writes the result to a temporary
// file. The path to the merged dictionary file is returned.
//
// Returns an error if the Redis lookup fails, if no dictionaries are found,
// or if any file operations fail.
func (d *DictGrabber) GrabDict(ctx context.Context, taskId, harness string) (string, error) {
	key := fmt.Sprintf(DictRedisKey, taskId, harness)

	// get the set of dict paths from redis
	dictPaths, err := d.redisClient.SMembers(ctx, key).Result()
	if err != nil {
		return "", fmt.Errorf("failed to get dict set from redis: %w", err)
	}
	if len(dictPaths) == 0 {
		return "", fmt.Errorf("no dicts found for harness %s in redis", harness)
	}

	d.logger.Info("Got dicts from Redis",
		zap.String("taskId", taskId),
		zap.String("harness", harness),
		zap.Int("numDicts", len(dictPaths)))

	var mergedLines []string
	for _, path := range dictPaths {
		content, err := os.ReadFile(path)
		if err != nil {
			return "", fmt.Errorf("failed to read dict file %s: %w", path, err)
		}
		lines := strings.Split(string(content), "\n")
		mergedLines = append(mergedLines, lines...)
	}

	// Deduplicate and write to a temporary merged dict file
	lineSet := make(map[string]struct{})
	var finalLines []string
	for _, line := range mergedLines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if _, ok := lineSet[line]; !ok {
			lineSet[line] = struct{}{}
			finalLines = append(finalLines, line)
		}
	}

	tmpFile, err := os.CreateTemp("", "merged_dict_*.dict")
	if err != nil {
		return "", fmt.Errorf("failed to create temp dict file: %w", err)
	}
	defer tmpFile.Close()

	_, err = tmpFile.WriteString(strings.Join(finalLines, "\n"))
	if err != nil {
		return "", fmt.Errorf("failed to write merged dict file: %w", err)
	}

	return tmpFile.Name(), nil
}

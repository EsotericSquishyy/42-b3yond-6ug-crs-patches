package corpus

import (
	"b3fuzz/internal/utils"
	"context"
	"fmt"
	"os"

	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

type CminSeedGrabber struct {
	redisClient    *redis.Client
	logger         *zap.Logger
	seedGrabberCtx context.Context
}

func NewCminSeedGrabber(redisClient *redis.Client, logger *zap.Logger, lifeCycle fx.Lifecycle) *CminSeedGrabber {
	// a context for the seed grabber. The context will be cancelled when the application stops
	seedGrabberCtx, cancel := context.WithCancel(context.Background())
	lifeCycle.Append(fx.Hook{
		OnStop: func(ctx context.Context) error {
			cancel()
			return nil
		},
	})

	return &CminSeedGrabber{
		redisClient,
		logger,
		seedGrabberCtx,
	}
}

// GetSeedsFromRedis retrieves seed files from Redis
func (s *CminSeedGrabber) GrabCorpusBlob(taskId, harness string) (string, error) {
	key := fmt.Sprintf("cmin:%s:%s", taskId, harness)

	// get the seed path from redis
	seedPath, err := s.redisClient.Get(s.seedGrabberCtx, key).Result()
	if err == redis.Nil {
		return "", fmt.Errorf("no seed found for harness %s in redis", harness)
	}
	if err != nil {
		return "", err
	}

	s.logger.Info("Got seed from legacy cmin",
		zap.String("taskId", taskId),
		zap.String("harness", harness),
		zap.String("seedPath", seedPath))

	// check if the seed path exists
	fileInfo, err := os.Stat(seedPath)
	if err != nil {
		if os.IsNotExist(err) {
			return "", fmt.Errorf("seed blob %s does not exist", seedPath)
		}
	}
	if fileInfo.Size() == 0 {
		return "", fmt.Errorf("seed bolb %s is empty", seedPath)
	}

	// check if the file is a valid .tar.gz file
	if !utils.IsTarGz(seedPath) {
		return "", fmt.Errorf("seed bolb %s is not a valid tar.gz file: %w", seedPath, err)
	}

	return seedPath, nil
}

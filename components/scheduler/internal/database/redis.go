package database

import (
	"context"
	"crs-scheduler/config"
	"strings"

	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

type RedisParams struct {
	fx.In

	Config *config.AppConfig
	Logger *zap.Logger
}

func NewRedisClient(p RedisParams) (*redis.Client, error) {
	redisSentinelHostsString := p.Config.RedisSentinelHosts
	redisSentinelHosts := strings.Split(redisSentinelHostsString, ",")

	client := redis.NewFailoverClient(&redis.FailoverOptions{
		MasterName:    p.Config.RedisMasterName,
		SentinelAddrs: redisSentinelHosts,
		DB:            0,
	})

	// Test the connection
	ctx := context.Background()
	if err := client.Ping(ctx).Err(); err != nil {
		p.Logger.Error("failed to connect to Redis", zap.Error(err))
		return nil, err
	}

	p.Logger.Info("connected to Redis")

	return client, nil
}

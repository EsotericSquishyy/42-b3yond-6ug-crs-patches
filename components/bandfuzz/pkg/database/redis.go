package database

import (
	"b3fuzz/config"
	"context"
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
	var client *redis.Client
	var err error

	if p.Config.RedisUrl != "" {
		client, err = newRedisClient(p.Config.RedisUrl)
	} else {
		client, err = newRedisFailoverClient(p.Config.RedisSentinelHosts, p.Config.RedisMasterName)
	}
	if err != nil {
		p.Logger.Error("Failed to create Redis client", zap.Error(err))
		return nil, err
	}

	p.Logger.Debug("Redis client created successfully")
	return client, nil
}

func newRedisFailoverClient(redisSentinelHostsString, redisMasterName string) (*redis.Client, error) {
	redisSentinelHosts := strings.Split(redisSentinelHostsString, ",")

	client := redis.NewFailoverClient(&redis.FailoverOptions{
		MasterName:    redisMasterName,
		SentinelAddrs: redisSentinelHosts,
		DB:            0,
	})

	// Test the connection
	ctx := context.Background()
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, err
	}

	return client, nil
}

func newRedisClient(redisUrl string) (*redis.Client, error) {
	options, err := redis.ParseURL(redisUrl)
	if err != nil {
		return nil, err
	}
	client := redis.NewClient(options)

	// Test the connection
	ctx := context.Background()
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, err
	}

	return client, nil
}

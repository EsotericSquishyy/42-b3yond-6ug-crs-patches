package config

import (
	"os"
	"strconv"
	"time"

	"github.com/joho/godotenv"
	"go.uber.org/zap"
)

type AppConfig struct {
	DatabaseURL        string
	RabbitMQURL        string
	RedisSentinelHosts string
	RedisMasterName    string
	RedisUrl           string
	LibCminHost        string
	LogLevel           string
	SchedulerConfig    SchedulerConfig
	CoreCount          int
	ServiceName        string
}

type SchedulerConfig struct {
	SchedulingInterval time.Duration `mapstructure:"scheduling_interval"`
	TasksPerBatch      int           `mapstructure:"tasks_per_batch"`
}

func LoadConfig() *AppConfig {
	// use a temporary logger for now
	logger := zap.NewExample().Named("config")

	godotenv.Load()

	config := &AppConfig{
		DatabaseURL:        os.Getenv("DATABASE_URL"),
		RabbitMQURL:        os.Getenv("RABBITMQ_URL"),
		RedisSentinelHosts: os.Getenv("REDIS_SENTINEL_HOSTS"),
		RedisMasterName:    os.Getenv("REDIS_MASTER"),
		RedisUrl:           os.Getenv("OVERRIDE_REDIS_URL"), // optional, for local dev
		LibCminHost:        os.Getenv("LIBCMIN_HOST"),
		LogLevel:           os.Getenv("LOG_LEVEL"),
		SchedulerConfig: SchedulerConfig{
			SchedulingInterval: parseDuration(os.Getenv("SCHEDULER_INTERVAL"), 10*time.Minute),
			TasksPerBatch:      parseInt(os.Getenv("SCHEDULER_TASKS_PER_BATCH"), 5),
		},
		CoreCount:   parseInt(os.Getenv("CORE_COUNT"), 16),
		ServiceName: os.Getenv("SERVICE_NAME"),
	}

	if config.LogLevel == "" {
		config.LogLevel = "info" // Set default log level
	}

	if config.DatabaseURL == "" {
		logger.Fatal("DATABASE_URL environment variable is required")
	}
	if config.RabbitMQURL == "" {
		logger.Fatal("RABBITMQ_URL environment variable is required")
	}
	if config.RedisSentinelHosts == "" {
		logger.Fatal("REDIS_SENTINEL_HOSTS environment variable is required")
	}
	if config.RedisMasterName == "" {
		logger.Fatal("REDIS_MASTER environment variable is required")
	}
	if config.ServiceName == "" {
		config.ServiceName = "b3fuzz" // Default service name
	}

	return config
}

func parseDuration(val string, defaultVal time.Duration) time.Duration {
	if val == "" {
		return defaultVal
	}
	d, err := time.ParseDuration(val)
	if err != nil {
		return defaultVal
	}
	return d
}

func parseInt(val string, defaultVal int) int {
	if val == "" {
		return defaultVal
	}
	i, err := strconv.Atoi(val)
	if err != nil {
		return defaultVal
	}
	return i
}

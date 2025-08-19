package config

import (
	"os"

	"github.com/joho/godotenv"
	"go.uber.org/zap"
)

type AppConfig struct {
	DatabaseURL                string
	RabbitMQURL                string
	RabbitMQManagementEndpoint string
	RedisSentinelHosts         string
	RedisMasterName            string
	LogLevel                   string

	CompetitionAPI CompetitionAPIConfig
	CrsAPI         CrsAPIConfig
}

type CompetitionAPIConfig struct {
	URL      string
	Username string
	Password string
}

type CrsAPIConfig struct {
	Username string
	Password string
}

func getEnv(key string, logger *zap.Logger) string {
	value := os.Getenv(key)
	if value == "" {
		logger.Fatal("required environment variable is not set", zap.String("key", key))
	}
	return value
}

func LoadConfig() *AppConfig {
	// use a temporary logger for now
	logger := zap.NewExample().Named("config")

	if err := godotenv.Load(); err != nil {
		logger.Info("No .env file found")
	}

	config := &AppConfig{
		DatabaseURL:                getEnv("DATABASE_URL", logger),
		RabbitMQURL:                getEnv("RABBITMQ_URL", logger),
		RabbitMQManagementEndpoint: getEnv("RABBITMQ_MANAGEMENT_ENDPOINT", logger),
		RedisSentinelHosts:         getEnv("REDIS_SENTINEL_HOSTS", logger),
		RedisMasterName:            getEnv("REDIS_MASTER", logger),
		LogLevel:                   os.Getenv("LOG_LEVEL"),

		CompetitionAPI: CompetitionAPIConfig{
			URL:      getEnv("COMPETITION_API_URL", logger),
			Username: getEnv("COMPETITION_API_KEY_ID", logger),
			Password: getEnv("COMPETITION_API_KEY_TOKEN", logger),
		},
		CrsAPI: CrsAPIConfig{
			Username: getEnv("CRS_KEY_ID", logger),
			Password: getEnv("CRS_KEY_TOKEN", logger),
		},
	}

	if config.LogLevel == "" {
		config.LogLevel = "info" // Set default log level
	}

	return config
}

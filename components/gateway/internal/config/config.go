package config

import (
	"fmt"
	"os"

	"github.com/joho/godotenv"
	"go.uber.org/fx"
	"go.uber.org/zap/zapcore"
)

// Config holds all configuration for the application
type Config struct {
	fx.Out

	LogLevel    zapcore.Level
	DatabaseURL string `name:"database_url"`
	Port        int    `name:"port"`
	Version     string `name:"version"`
}

// NewConfig loads configuration from environment variables
func NewConfig() (Config, error) {
	// Load .env file if it exists
	_ = godotenv.Load()

	config := Config{}

	// Configure logging
	logLevel := os.Getenv("LOG_LEVEL")
	if logLevel == "" {
		logLevel = "info"
	}

	switch logLevel {
	case "debug":
		config.LogLevel = zapcore.DebugLevel
	case "info":
		config.LogLevel = zapcore.InfoLevel
	default:
		config.LogLevel = zapcore.WarnLevel
	}

	// Configure database
	config.DatabaseURL = os.Getenv("DATABASE_URL")
	if config.DatabaseURL == "" {
		return Config{}, fmt.Errorf("DATABASE_URL is required")
	}

	// Configure port
	config.Port = 8080

	// Configure version
	config.Version = os.Getenv("VERSION")
	if config.Version == "" {
		config.Version = "VERSION_UNAVAILABLE"
	}

	return config, nil
}

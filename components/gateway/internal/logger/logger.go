package logger

import (
	"go.uber.org/fx"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

type Params struct {
	fx.In

	LogLevel zapcore.Level
}

func NewLogger(p Params) (*zap.Logger, error) {
	// production mode
	if p.LogLevel == zapcore.WarnLevel {
		config := zap.NewProductionConfig()
		config.Level = zap.NewAtomicLevelAt(p.LogLevel)
		return config.Build()
	}

	// development mode, more detailed logging
	config := zap.NewDevelopmentConfig()
	config.Level = zap.NewAtomicLevelAt(p.LogLevel)
	config.EncoderConfig.EncodeLevel = zapcore.CapitalColorLevelEncoder

	return config.Build()
}

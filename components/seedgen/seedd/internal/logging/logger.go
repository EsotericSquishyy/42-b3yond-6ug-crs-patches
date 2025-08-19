package logging

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

var (
	// Global logger instance
	Logger *zap.Logger
)

// InitLogger initializes the global logger
func InitLogger(debug bool) error {
	config := zap.NewProductionConfig()

	// Set log level based on debug flag
	if debug {
		config.Level = zap.NewAtomicLevelAt(zap.DebugLevel)
	}

	// Configure logging format
	config.EncoderConfig.TimeKey = "timestamp"
	config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	config.EncoderConfig.StacktraceKey = "" // Disable stacktrace by default

	var err error
	Logger, err = config.Build(
		zap.AddCallerSkip(1),
		zap.AddCaller(),
	)
	if err != nil {
		return err
	}

	return nil
}

// Sync flushes any buffered log entries
func Sync() error {
	if Logger != nil {
		return Logger.Sync()
	}
	return nil
}

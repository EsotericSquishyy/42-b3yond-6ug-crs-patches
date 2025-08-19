package main

import (
	"b3fuzz/config"
	"b3fuzz/internal/builder"
	"b3fuzz/internal/seeds"
	"b3fuzz/pkg/database"
	"b3fuzz/pkg/logger"
	"b3fuzz/pkg/mq"
	"b3fuzz/pkg/telemetry"
	"context"

	_ "go.uber.org/automaxprocs"
	"go.uber.org/fx"
	"go.uber.org/fx/fxevent"
	"go.uber.org/zap"
)

func NewAppContext(lc fx.Lifecycle) context.Context {
	ctx, cancel := context.WithCancel(context.Background())
	lc.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			return nil
		},
		OnStop: func(ctx context.Context) error {
			cancel()
			return nil
		},
	})
	return ctx
}

func main() {
	app := fx.New(
		fx.Provide(
			NewAppContext,              // inject app context
			config.LoadConfig,          // inject config
			logger.NewLogger,           // inject logger
			telemetry.NewTelemetry,     // inject telemetry
			telemetry.NewTracerFactory, // inject telemetry tracer factory
			database.NewRedisClient,    // inject redis client
			seeds.NewSeedManager,       // inject seed manager
			mq.NewRabbitMQ,             // inject rabbitmq service
			database.NewDBConnection,   // inject db connection
		),
		fx.Invoke(
			builder.StartTaskBuilder,
		),
		fx.WithLogger(func(log *zap.Logger) fxevent.Logger {
			return &fxevent.ZapLogger{Logger: log}
		}),
	)
	app.Run()
}

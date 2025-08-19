package main

import (
	"crs-scheduler/config"
	"crs-scheduler/internal/api"
	"crs-scheduler/internal/database"
	"crs-scheduler/internal/logger"
	"crs-scheduler/internal/messaging"
	"crs-scheduler/internal/scheduler"
	"crs-scheduler/internal/telemetry"
	"crs-scheduler/repository"
	"crs-scheduler/service"

	"go.uber.org/fx"
)

func main() {
	app := fx.New(
		fx.Provide(
			config.LoadConfig,          // inject config
			logger.NewLogger,           // inject logger
			database.NewDBConnection,   // inject db connection
			messaging.NewRabbitMQ,      // inject rabbitmq service
			database.NewRedisClient,    // inject redis service
			telemetry.NewTelemetry,     // inject telemetry service
			telemetry.NewTracerFactory, // inject tracer factory
		),
		repository.Module,
		service.Module,
		api.Module,
		fx.Invoke(
			messaging.InitializeMQ,
			scheduler.NewScheduler,
		),
	)
	app.Run()
}

package main

import (
	"context"
	"crs-gateway/gen/restapi"
	"crs-gateway/internal/config"
	"crs-gateway/internal/db"
	"crs-gateway/internal/handlers"
	"crs-gateway/internal/logger"
	"crs-gateway/internal/middle"
	"crs-gateway/internal/server"
	"crs-gateway/internal/services"

	"go.uber.org/fx"
	"go.uber.org/zap"
)

func serverLifecycle(lc fx.Lifecycle, server *restapi.Server, logger *zap.Logger) {
	lc.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			go func() { // non-blocking server start
				if err := server.Serve(); err != nil {
					logger.Error("server failed to start", zap.Error(err))
				}
			}()
			return nil
		},
		OnStop: func(ctx context.Context) error {
			return server.Shutdown()
		},
	})
}

func main() {
	app := fx.New(
		fx.Provide(
			config.NewConfig,
			logger.NewLogger,
			server.NewServer,
			server.NewAuthenticator,
			db.NewDBConnection,
		),
		fx.Invoke(
			serverLifecycle,
		),
		handlers.Module,
		middle.Module,
		services.Module,
	)
	app.Run()
}

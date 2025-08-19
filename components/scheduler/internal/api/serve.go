package api

import (
	"context"
	"crs-scheduler/config"
	"net/http"

	"go.uber.org/fx"
	"go.uber.org/zap"
)

type ServerParams struct {
	fx.In
	Lifecycle      fx.Lifecycle
	HealthService  *HealthService
	StatusService  *StatusService
	QueueService   *QueueService
	HarnessService *HarnessService
	Logger         *zap.Logger
	Config         *config.AppConfig
}

// NewAPIServer creates a new HTTP server for API endpoints.
func NewAPIServer(params ServerParams) *http.Server {
	mux := http.NewServeMux()

	// Health endpoint
	mux.HandleFunc("/health", handleHealth(params.HealthService, params.Logger))

	// Status endpoint
	mux.HandleFunc("/status", handleStatus(params.StatusService, params.Logger))

	// Queue endpoint
	mux.HandleFunc("/queue", handleQueue(params.QueueService, params.Logger))

	// Harness endpoint
	mux.HandleFunc("/harness", handleHarness(params.HarnessService, params.Logger))

	server := &http.Server{
		Addr:    ":8080",
		Handler: mux,
	}

	// Start health check goroutines
	go func() {
		if err := params.HealthService.createCrsUser(params.Logger, params.Config); err != nil {
			params.Logger.Error("failed to create CRS user", zap.Error(err))
		}
	}()

	go func() {
		if err := params.HealthService.waitForCompetitionAPI(params.Logger, params.Config); err != nil {
			params.Logger.Fatal("failed to wait for competition API", zap.Error(err))
		}
	}()

	// Register lifecycle hooks
	params.Lifecycle.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			go func() {
				if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
					params.Logger.Fatal("failed to start API server", zap.Error(err))
				}
			}()
			return nil
		},
		OnStop: func(ctx context.Context) error {
			return server.Shutdown(ctx)
		},
	})

	return server
}

var Module = fx.Module("api",
	fx.Provide(
		NewHealthService,
		NewStatusService,
		NewQueueService,
		NewHarnessService,
	),
	fx.Invoke(
		NewAPIServer,
	),
)

// Package server implements the gRPC server for the SeedD service.
package server

import (
	"BugBuster/SeedD/internal/logging"
	"BugBuster/SeedD/internal/runtime"
	"context"
	"fmt"
	"net"

	"go.uber.org/zap"
	"google.golang.org/grpc"
	_ "google.golang.org/grpc/encoding/gzip"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"

	"BugBuster/SeedD/internal/service"
)

const (
	// DefaultPort is the default port for the gRPC server
	DefaultPort = 9002
	// MaxMessageSize defines the maximum message size for gRPC (1GB)
	MaxMessageSize = 1024 * 1024 * 1024
)

// Server represents the gRPC server implementation
type Server struct {
	runtime.UnimplementedSeedDServer
	runSeedsService *service.RunSeedsService
}

// NewServer creates a new instance of the Server
func NewServer(compilationDatabasePath string) *Server {
	return &Server{
		runSeedsService: service.NewRunSeedsService(),
	}
}

// RunSeeds delegates the seed running operation to the RunSeedsService
func (s *Server) RunSeeds(ctx context.Context, req *runtime.RunSeedsRequest) (*runtime.RunSeedsResponse, error) {
	return s.runSeedsService.RunSeeds(ctx, req)
}

// GetMergedCoverage retrieves merged coverage information
func (s *Server) GetMergedCoverage(ctx context.Context, req *runtime.GetMergedCoverageRequest) (*runtime.RunSeedsResponse, error) {
	return s.runSeedsService.GetMergedCoverage(ctx, req)
}

// GetRegionSource retrieves the source code for a specific region
func (s *Server) GetRegionSource(ctx context.Context, req *runtime.GetRegionSourceRequest) (*runtime.GetRegionSourceResponse, error) {
	// TODO: Merge to some service instead of using it statically
	return service.GetRegionSource(ctx, req)
}

// GetCallGraph retrieves the call graph for the specified request
func (s *Server) GetCallGraph(ctx context.Context, req *runtime.GetCallGraphRequest) (*runtime.GetCallGraphResponse, error) {
	return s.runSeedsService.GetCallGraph(ctx, req)
}

// GetFunctions retrieves function information
func (s *Server) GetFunctions(ctx context.Context, req *runtime.GetFunctionsRequest) (*runtime.GetFunctionsResponse, error) {
	// TODO: Merge to some service instead of using it statically
	return service.GetFunctions(ctx, req)
}

// Serve starts the gRPC server with graceful shutdown support
func Serve(ctx context.Context, compilation_database_path string) error {
	addr := fmt.Sprintf(":%d", DefaultPort)
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to listen: %w", err)
	}

	opts := []grpc.ServerOption{
		grpc.MaxRecvMsgSize(MaxMessageSize),
		grpc.MaxSendMsgSize(MaxMessageSize),
	}

	grpcServer := grpc.NewServer(opts...)
	runtime.RegisterSeedDServer(grpcServer, NewServer(compilation_database_path))

	// Setup health check
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus("seedd", grpc_health_v1.HealthCheckResponse_SERVING)

	// Start server
	logging.Logger.Info("Starting gRPC server",
		zap.String("address", addr),
		zap.Int("port", DefaultPort),
	)

	// Handle graceful shutdown
	go func() {
		<-ctx.Done()
		logging.Logger.Info("Shutting down gRPC server...")
		grpcServer.GracefulStop()
	}()

	if err := grpcServer.Serve(lis); err != nil {
		return fmt.Errorf("failed to serve: %w", err)
	}

	return nil
}

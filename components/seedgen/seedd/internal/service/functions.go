package service

import (
	"BugBuster/SeedD/internal/logging"
	"BugBuster/SeedD/internal/runtime"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"go.uber.org/zap"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func runGetCovAll(harnessBinary string) (string, error) {
	// Create a temporary seed file, use /tmp/getcov-hi
	seedFile := "/tmp/getcov-hi"
	// Check if the seed file exists
	if _, err := os.Stat(seedFile); os.IsNotExist(err) {
		// Create the seed file and write "hi" to it
		err := os.WriteFile(seedFile, []byte("hi"), 0644)
		if err != nil {
			return "", fmt.Errorf("failed to create seed file: %v", err)
		}
	}
	defer os.Remove(seedFile)

	getcovCmd := exec.Command("/getcov", "--all", "--", filepath.Join("/out", harnessBinary), seedFile)
	getcovCmd.Dir = artifactDir

	output, err := getcovCmd.Output()
	if err != nil {
		return "", fmt.Errorf("failed to run getcov: %v\nOutput: %s", err, string(output))
	}

	return string(output), nil
}

func GetFunctions(ctx context.Context, req *runtime.GetFunctionsRequest) (*runtime.GetFunctionsResponse, error) {
	logger := logging.Logger.With(
		zap.String("harness_binary", req.HarnessBinary),
	)

	if err := checkGetCovBinary(); err != nil {
		logger.Error("Failed to check getcov binary",
			zap.String("harness_binary", req.HarnessBinary),
			zap.Error(err),
		)
		return nil, status.Error(codes.Unavailable, err.Error())
	}

	output, err := runGetCovAll(req.HarnessBinary)
	if err != nil {
		logger.Error("Failed to run getcov",
			zap.String("harness_binary", req.HarnessBinary),
			zap.Error(err),
		)
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &runtime.GetFunctionsResponse{
		Functions: output,
	}, nil
}

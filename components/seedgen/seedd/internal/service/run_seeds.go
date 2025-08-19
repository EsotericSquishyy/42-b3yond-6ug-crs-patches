package service

import (
	"BugBuster/SeedD/internal/logging"
	"BugBuster/SeedD/internal/runtime"
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"

	"go.uber.org/zap"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const (
	artifactDir  = "/out"
	getCovBinary = "/getcov"
)

// GetCovConfig holds the configuration for running coverage analysis.
type GetCovConfig struct {
	HarnessBinary string   // Path to the harness binary
	SeedsPaths    []string // List of paths to seed files
}

// RunSeedsService implements the seed-running service.
type RunSeedsService struct {
	mergedProfdataPath map[string]string     // key: harness binary, value: merged profdata path
	callGraphs         map[string]*CallGraph // key: harness binary, value: call graph

	callGraphUpdateMutex sync.Mutex // Ensures the call graph is updated atomically
}

// NewRunSeedsService creates a new instance of RunSeedsService.
func NewRunSeedsService() *RunSeedsService {
	return &RunSeedsService{
		mergedProfdataPath: make(map[string]string),
		callGraphs:         make(map[string]*CallGraph),
	}
}

// RunSeeds executes the seed files and collects coverage information.
func (s *RunSeedsService) RunSeeds(ctx context.Context, req *runtime.RunSeedsRequest) (*runtime.RunSeedsResponse, error) {
	logger := logging.Logger.With(
		zap.String("harness_binary", req.HarnessBinary),
		zap.Int("seeds_count", len(req.SeedsPath)),
	)
	logger.Info("Starting seed execution")

	// Validate input paths, run seeds dry-run, and check getcov availability.
	if err := s.validateAndPrepare(req.HarnessBinary, req.SeedsPath); err != nil {
		logger.Error("Failed to validate and prepare environment", zap.Error(err))
		return nil, err
	}

	config := &GetCovConfig{
		HarnessBinary: req.HarnessBinary,
		SeedsPaths:    req.SeedsPath,
	}

	coverage, report, profdataPath, err := config.RunAndParseCoverage()
	if err != nil {
		logger.Error("Failed to run getcov and parse output", zap.Error(err))
		return nil, status.Error(codes.Internal, err.Error())
	}

	// Write report to a file under /shared
	reportFilePath := filepath.Join("/shared", "getcov_report.txt")
	if err := os.WriteFile(reportFilePath, []byte(report), 0644); err != nil {
		logger.Error("Failed to write report to file",
			zap.String("file_path", reportFilePath),
			zap.Error(err),
		)
		return nil, status.Error(codes.Internal, fmt.Sprintf("failed to write report to file: %v", err))
	}

	// Merge the newly generated .profdata into the overall merged profile.
	if err := s.mergeProfdata(req.HarnessBinary, profdataPath); err != nil {
		logger.Error("Failed to merge profdata",
			zap.String("profdata_path", profdataPath),
			zap.Error(err),
		)
		return nil, status.Error(codes.Internal, err.Error())
	}

	logger.Info("Successfully completed seed execution")
	return &runtime.RunSeedsResponse{
		Coverage: coverage,
		Report:   "getcov_report.txt",
	}, nil
}

// GetMergedCoverage returns the final merged coverage for a given harness binary.
func (s *RunSeedsService) GetMergedCoverage(ctx context.Context, req *runtime.GetMergedCoverageRequest) (*runtime.RunSeedsResponse, error) {
	logger := logging.Logger.With(
		zap.String("harness_binary", req.HarnessBinary),
	)
	logger.Info("Getting merged coverage")

	mergedProfdataPath, ok := s.mergedProfdataPath[req.HarnessBinary]
	if !ok {
		return nil, status.Error(codes.NotFound, "merged profdata path not found")
	}

	getcovCmd := exec.Command(
		getCovBinary,
		"--hybrid",
		"--profdata",
		mergedProfdataPath,
		"--",
		filepath.Join("/out", req.HarnessBinary),
		"@@",
	)
	getcovCmd.Dir = artifactDir

	output, err := getcovCmd.Output()
	if err != nil {
		logger.Error("Failed to run getcov",
			zap.Error(err),
			zap.String("output", string(output)),
		)
		return nil, status.Errorf(codes.Internal, "failed to run getcov: %v\nOutput: %s", err, string(output))
	}

	coverage, report, _, err := parseCoverageOutput(string(output))
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to parse getcov output: %v", err)
	}

	// Write report to a file under /shared
	reportFilePath := filepath.Join("/shared", "getcov_merged_report.txt")
	if err := os.WriteFile(reportFilePath, []byte(report), 0644); err != nil {
		logger.Error("Failed to write report to file",
			zap.String("file_path", reportFilePath),
			zap.Error(err),
		)
		return nil, status.Error(codes.Internal, fmt.Sprintf("failed to write report to file: %v", err))
	}

	logging.Logger.Info("Successfully retrieved merged coverage")

	return &runtime.RunSeedsResponse{
		Coverage: coverage,
		Report:   "getcov_merged_report.txt",
	}, nil
}

// validateAndPrepare ensures all paths are valid, seeds can be run, and getcov is accessible.
func (s *RunSeedsService) validateAndPrepare(harnessBinary string, seedsPaths []string) error {
	// 1. Check harness binary and seed file paths.
	if err := validatePaths(harnessBinary, seedsPaths); err != nil {
		logging.Logger.Error("Failed to validate paths", zap.Error(err))
		return status.Error(codes.NotFound, err.Error())
	}

	// 2. Ensure getcov is available.
	if err := checkGetCovBinary(); err != nil {
		logging.Logger.Error("Getcov binary not found", zap.Error(err))
		return status.Error(codes.Unavailable, err.Error())
	}

	// 3. Dry-run seeds.
	if err := s.dryRunSeeds(harnessBinary, seedsPaths); err != nil {
		logging.Logger.Error("Failed to dry-run seeds", zap.Error(err))
		return status.Error(codes.Internal, err.Error())
	}

	return nil
}

// mergeProfdata merges a newly generated .profdata into the existing merged profdata for a harness binary.
func (s *RunSeedsService) mergeProfdata(harnessBinary string, profdataPath string) error {
	// If we already have a merged .profdata, merge the new one with the existing.
	if mergedProfdataPath, ok := s.mergedProfdataPath[harnessBinary]; ok {
		mergeCmd := exec.Command(
			"llvm-profdata",
			"merge",
			"-o", mergedProfdataPath,
			profdataPath,
			mergedProfdataPath,
		)
		return mergeCmd.Run()
	}

	// Otherwise, create a new merged .profdata for this harness binary.
	mergedProfdataFilename := fmt.Sprintf("merged_%s.profdata", filepath.Base(harnessBinary))
	mergedProfdataFullPath := filepath.Join(artifactDir, mergedProfdataFilename)
	s.mergedProfdataPath[harnessBinary] = mergedProfdataFullPath

	return copyFile(profdataPath, mergedProfdataFullPath)
}

// RunAndParseCoverage runs getcov using the config and parses its output.
func (c *GetCovConfig) RunAndParseCoverage() (coverage, report, profdataPath string, err error) {
	output, err := c.runGetCov()
	if err != nil {
		return "", "", "", err
	}
	return parseCoverageOutput(output)
}

// runGetCov executes the getcov tool with the current config.
func (c *GetCovConfig) runGetCov() (string, error) {
	logger := logging.Logger.With(
		zap.String("harness_binary", c.HarnessBinary),
		zap.Int("seeds_count", len(c.SeedsPaths)),
	)

	// Prepare a temp directory with seed files.
	tmpDir, err := prepareSeedDirectory(c.SeedsPaths)
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(tmpDir)
	logger.Debug("Prepared seed directory", zap.String("tmp_dir", tmpDir))

	// Construct getcov arguments.
	// args := []string{"-i", tmpDir, "--hybrid", "--", filepath.Join("/out", c.HarnessBinary), "@@"}
	// logger.Info("Running getcov", zap.Strings("args", args))

	args := []string{"--hybrid", "--", filepath.Join("/out", c.HarnessBinary)}

	files, err := os.ReadDir(tmpDir)
	if err != nil {
		logger.Fatal("Failed to read tmpDir", zap.Error(err))
	}

	for _, file := range files {
		if !file.IsDir() {
			filePath := filepath.Join(tmpDir, file.Name())
			args = append(args, filePath)
		}
	}

	// Run getcov command.
	getcovCmd := exec.Command(getCovBinary, args...)
	getcovCmd.Dir = artifactDir

	output, err := getcovCmd.Output()
	if err != nil {
		logger.Error("Failed to run getcov",
			zap.Error(err),
			zap.String("output", string(output)),
		)
		return "", fmt.Errorf("failed to run getcov: %v\nOutput: %s", err, string(output))
	}

	logger.Info("Successfully executed getcov")
	return string(output), nil
}

// parseCoverageOutput parses the output from getcov into coverage, report, and profdata path.
func parseCoverageOutput(output string) (coverage, report, profdataPath string, err error) {
	parts := strings.Split(output, "\n<<<JSON_OUTPUT_END>>>\n")
	if len(parts) != 2 {
		return "", "", "", fmt.Errorf("invalid getcov output format (missing JSON_OUTPUT_END marker)")
	}

	coverage = parts[0]
	remaining := parts[1]

	parts = strings.Split(remaining, "\n<<<TEXT_OUTPUT_END>>>\n")
	if len(parts) != 2 {
		return "", "", "", fmt.Errorf("invalid getcov output format (missing TEXT_OUTPUT_END marker)")
	}

	report = parts[0]
	profdataPath = strings.TrimSpace(parts[1])

	return coverage, report, profdataPath, nil
}

// validatePaths checks if the harness binary and seed files exist.
func validatePaths(harnessBinary string, seedsPaths []string) error {
	logger := logging.Logger

	// Convert to absolute path if needed.
	if !filepath.IsAbs(harnessBinary) {
		harnessBinary = filepath.Join(artifactDir, harnessBinary)
		logger.Debug("Converting harness binary to absolute path", zap.String("harness_binary", harnessBinary))
	}

	if _, err := os.Stat(harnessBinary); os.IsNotExist(err) {
		logger.Error("Harness binary not found", zap.String("path", harnessBinary))
		return fmt.Errorf("harness binary not found at path: %s", harnessBinary)
	}

	for _, seedPath := range seedsPaths {
		if _, err := os.Stat(seedPath); os.IsNotExist(err) {
			logger.Error("Seed file not found", zap.String("path", seedPath))
			return fmt.Errorf("seed file not found at path: %s", seedPath)
		}
	}

	logger.Debug("All paths validated successfully")
	return nil
}

// checkGetCovBinary verifies that the getcov binary exists and is accessible.
func checkGetCovBinary() error {
	if _, err := os.Stat(getCovBinary); os.IsNotExist(err) {
		log.Printf("Error: getcov binary not found")
		return fmt.Errorf("getcov binary not found at path: %s", getCovBinary)
	}
	return nil
}

// prepareSeedDirectory creates a temporary directory and copies all seed files into it.
func prepareSeedDirectory(seedsPaths []string) (string, error) {
	logger := logging.Logger

	tmpDir, err := os.MkdirTemp("", "seeds-*")
	if err != nil {
		logger.Error("Failed to create temporary directory", zap.Error(err))
		return "", fmt.Errorf("failed to create temporary directory: %v", err)
	}
	logger.Debug("Created temporary directory", zap.String("path", tmpDir))

	for _, seedPath := range seedsPaths {
		seedName := filepath.Base(seedPath)
		destPath := filepath.Join(tmpDir, seedName)

		if err := copyFile(seedPath, destPath); err != nil {
			logger.Error("Failed to copy seed file",
				zap.String("source", seedPath),
				zap.String("destination", destPath),
				zap.Error(err),
			)
			os.RemoveAll(tmpDir)
			return "", fmt.Errorf("failed to copy seed %s: %v", seedPath, err)
		}
		logger.Debug("Copied seed file",
			zap.String("source", seedPath),
			zap.String("destination", destPath),
		)
	}

	return tmpDir, nil
}

// copyFile copies a file from src to dst, overwriting if necessary.
func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0644)
}

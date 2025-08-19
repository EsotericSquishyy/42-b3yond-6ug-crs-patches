package builder

import (
	"b3fuzz/internal/types"
	"b3fuzz/internal/utils"
	"b3fuzz/pkg/telemetry"
	"bufio"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"go.opentelemetry.io/otel/codes"
	"go.uber.org/zap"
)

type BuildConfig struct {
	sanitizer         string            // "address", "undefined", "memory"
	fuzzEngine        string            // "afl", "libfuzzer"
	extraEnvironments map[string]string // optional
}

func (b *TaskBuilder) compile_with_retry(ctx context.Context, taskDetails *TaskDetails, c BuildConfig) ([]string, error) {
	var err error
	for i := range 3 { // Retry up to 3 times
		harnesses, err := b.compile(ctx, taskDetails, c)
		if err == nil {
			return harnesses, nil
		}
		b.logger.Warn("Compilation failed, retrying", zap.Int("attempt", i+1), zap.Error(err))
	}
	return nil, fmt.Errorf("failed to compile after retries: %w", err)
}

// compile prepares and builds the fuzzing project
// returns the path to all fuzzing harnesses
func (b *TaskBuilder) compile(ctx context.Context, taskDetails *TaskDetails, c BuildConfig) ([]string, error) {
	buildTracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	span := fmt.Sprintf("compiling with %s sanitizer", c.sanitizer)
	compileTracer := buildTracer.Spawn(span).WithAttributes(
		telemetry.EmptySpanAttributes(),
	)
	compileTracer.Start()
	defer compileTracer.End()

	compileCtx := context.WithValue(ctx, telemetry.TracerKey{}, compileTracer)

	// Check if Docker is available
	if err := checkDockerAvailability(compileCtx); err != nil {
		b.logger.Error("Docker not available", zap.Error(err))
		return nil, fmt.Errorf("docker not available: %w", err)
	}

	projectName := taskDetails.ProjectName

	// Check if Dockerfile exists
	dockerfilePath := filepath.Join(taskDetails.FuzzToolingPath, "projects", projectName, "Dockerfile")
	if _, err := os.Stat(dockerfilePath); os.IsNotExist(err) {
		b.logger.Error("Dockerfile not found", zap.String("path", dockerfilePath))
		return nil, fmt.Errorf("dockerfile not found in project directory: %w", err)
	}

	// Build the Docker image
	if err := b.buildDockerImage(compileCtx, taskDetails); err != nil {
		compileTracer.SetStatus(codes.Error, "Failed to build Docker image")
		return nil, fmt.Errorf("failed to build docker image: %w", err)
	}

	// Build the fuzzers
	if err := b.buildFuzzers(compileCtx, taskDetails, c); err != nil {
		compileTracer.SetStatus(codes.Error, "Failed to build fuzzers")
		return nil, fmt.Errorf("failed to build fuzzers: %w", err)
	}

	harnesses := b.discoverFuzzTargets(taskDetails)
	if harnesses == nil {
		// discoverFuzzTargets logs the error internally
		compileTracer.SetStatus(codes.Error, "Failed to find fuzz targets")
		return nil, fmt.Errorf("failed to discover fuzz targets for sanitizer %s", c.sanitizer)
	}

	b.logger.Info("Successfully compiled project for sanitizer",
		zap.String("taskID", taskDetails.TaskID),
		zap.String("sanitizer", c.sanitizer),
		zap.Strings("harnesses", harnesses))

	compileTracer.SetStatus(codes.Ok, "Compilation successful")
	return harnesses, nil
}

// buildDockerImage builds the Docker image for the project
func (b *TaskBuilder) buildDockerImage(ctx context.Context, taskDetails *TaskDetails) error {
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	buildImageTracer := tracer.Spawn("building docker image").WithAttributes(
		telemetry.EmptySpanAttributes(),
	)
	buildImageTracer.Start()
	defer buildImageTracer.End()

	projectName := taskDetails.ProjectName
	b.logger.Info("Building Docker image", zap.String("project", projectName))

	buildImageArgs := []string{
		filepath.Join(taskDetails.FuzzToolingPath, "infra", "helper.py"),
		"build_image",
		"--no-pull",
		projectName,
	}

	buildImageCmd := exec.CommandContext(
		ctx,
		"python3",
		buildImageArgs...,
	)

	// Log the command for debugging
	b.logger.Debug("Running build image command",
		zap.String("command", buildImageCmd.String()))

	buildImageCmd.Stdout = os.Stdout
	buildImageCmd.Stderr = os.Stderr
	buildImageCmd.Env = filterOtelEnv(os.Environ()) // Filter out OpenTelemetry related env vars

	if err := buildImageCmd.Run(); err != nil {
		b.logger.Error("Failed to build Docker image", zap.Error(err))
		buildImageTracer.AddEvent("build_image_failed", telemetry.EventAttributes{})
		return fmt.Errorf("build docker image: %w", err)
	}

	return nil
}

// buildFuzzers builds the fuzzers for the project
func (b *TaskBuilder) buildFuzzers(ctx context.Context, taskDetails *TaskDetails, c BuildConfig) error {
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	buildFuzzerTracer := tracer.Spawn("building fuzzers").WithAttributes(
		telemetry.EmptySpanAttributes(),
	)
	buildFuzzerTracer.Start()
	defer buildFuzzerTracer.End()

	projectName := taskDetails.ProjectName
	b.logger.Info("Building fuzzers",
		zap.String("project", projectName),
		zap.String("sanitizer", c.sanitizer))

	buildFuzzersArgs := []string{
		filepath.Join(taskDetails.FuzzToolingPath, "infra", "helper.py"),
		"build_fuzzers",
		"--clean",
	}

	// apply the extra environments
	for name, value := range c.extraEnvironments {
		buildFuzzersArgs = append(buildFuzzersArgs, "-e", fmt.Sprintf("%s=%s", name, value))
	}

	if c.fuzzEngine != "" {
		buildFuzzersArgs = append(buildFuzzersArgs, fmt.Sprintf("--engine=%s", c.fuzzEngine))
	}

	if c.sanitizer != "" {
		buildFuzzersArgs = append(buildFuzzersArgs, fmt.Sprintf("--sanitizer=%s", c.sanitizer))
	}

	buildFuzzersArgs = append(buildFuzzersArgs, projectName, taskDetails.RepoPath)

	buildFuzzersCmd := exec.CommandContext(
		ctx,
		"python3",
		buildFuzzersArgs...,
	)

	// Log the command for debugging
	b.logger.Debug("Running build fuzzers command",
		zap.String("command", buildFuzzersCmd.String()))

	buildFuzzersCmd.Stdout = os.Stdout
	buildFuzzersCmd.Stderr = os.Stderr
	buildFuzzersCmd.Env = filterOtelEnv(os.Environ()) // Filter out OpenTelemetry related env vars

	if err := buildFuzzersCmd.Run(); err != nil {
		b.logger.Error("Failed to build fuzzers", zap.Error(err))
		buildFuzzerTracer.AddEvent("build_fuzzers_failed", telemetry.EventAttributes{})
		return fmt.Errorf("build fuzzers: %w", err)
	}

	return nil
}

// checkDockerAvailability verifies that Docker is running and available
func checkDockerAvailability(ctx context.Context) error {
	cmd := exec.CommandContext(ctx, "docker", "ps")
	cmd.Env = filterOtelEnv(os.Environ()) // Filter out OpenTelemetry related env vars
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("docker not available: %w", err)
	}
	return nil
}

func (b *TaskBuilder) discoverFuzzTargets(taskDetails *TaskDetails) []string {
	// check if <fuzz tooling>/build/out/<project name> exists
	buildOutputDir := filepath.Join(taskDetails.FuzzToolingPath, "build", "out", taskDetails.ProjectName)
	if _, err := os.Stat(buildOutputDir); os.IsNotExist(err) {
		b.logger.Error("Fuzz targets directory not found", zap.String("path", buildOutputDir))
		return nil
	}

	// read all files in the fuzz targets directory
	files, err := os.ReadDir(buildOutputDir)
	if err != nil {
		b.logger.Error("Failed to read fuzz targets directory", zap.String("path", buildOutputDir), zap.Error(err))
		return nil
	}

	// filter out non-executable files
	var executables []string
	for _, file := range files {
		info, err := file.Info()
		if err != nil {
			b.logger.Error("Failed to get file info", zap.String("file", file.Name()), zap.Error(err))
			continue
		}
		if info.Mode().IsRegular() && info.Mode()&0111 != 0 {
			executables = append(executables, file.Name())
		}
	}

	// run "strings" on each potential fuzz target, and filter out the ones that don't contain "LLVMFuzzerTestOneInput"
	var harnesses []string
	for _, binary := range executables {
		cmd := exec.Command("strings", filepath.Join(buildOutputDir, binary))
		output, err := cmd.Output()
		if err != nil {
			b.logger.Error("Failed to run strings on fuzz target", zap.String("target", binary), zap.Error(err))
			continue
		}
		if strings.Contains(string(output), "LLVMFuzzerTestOneInput") {
			harnesses = append(harnesses, filepath.Join(buildOutputDir, binary))
		}
	}

	// return the fuzz targets
	return harnesses
}

// discoverFuzzCorpus checks for seed_corpus.zip files in the build output directory
// if it finds any, it will send them to the cmin component
func (b *TaskBuilder) discoverFuzzCorpus(taskDetails *TaskDetails) error {
	// check if <fuzz tooling>/build/out/<project name> exists
	buildOutputDir := filepath.Join(taskDetails.FuzzToolingPath, "build", "out", taskDetails.ProjectName)
	if _, err := os.Stat(buildOutputDir); os.IsNotExist(err) {
		b.logger.Error("Fuzz targets directory not found", zap.String("path", buildOutputDir))
		return nil
	}

	// read all files in the fuzz targets directory
	files, err := os.ReadDir(buildOutputDir)
	if err != nil {
		b.logger.Error("Failed to read fuzz targets directory", zap.String("path", buildOutputDir), zap.Error(err))
		return nil
	}

	seedZips := make(map[string]string)
	for _, file := range files {
		if strings.HasSuffix(file.Name(), "_seed_corpus.zip") {
			harnessName := strings.TrimSuffix(file.Name(), "_seed_corpus.zip")
			seedZips[harnessName] = filepath.Join(buildOutputDir, file.Name())
		}
	}

	if len(seedZips) == 0 {
		b.logger.Info("No seed corpus files found in build output directory")
		return nil
	}

	seedChan := make(chan types.SeedMessage, 100)
	defer close(seedChan)
	b.seedManager.RegisterSeedChan(seedChan)

	totalSeeds := 0
	for harnessName, zipPath := range seedZips {
		fakeFuzzlet := &types.Fuzzlet{
			TaskId:       taskDetails.TaskID,
			Harness:      harnessName,
			Sanitizer:    "fake",
			FuzzEngine:   "fake",
			ArtifactPath: "fake",
		}

		// unzip the seed corpus to a temporary directory
		tmpDir, err := os.MkdirTemp("", "builtin_seed_corpus_*")
		if err != nil {
			b.logger.Error("Failed to create temporary directory for seed corpus", zap.Error(err))
			return fmt.Errorf("create temp dir: %w", err)
		}
		defer os.RemoveAll(tmpDir) // Clean up temp directory

		if err := utils.Unzip(zipPath, tmpDir); err != nil {
			b.logger.Error("Failed to unzip seed corpus", zap.String("path", zipPath), zap.Error(err))
			return fmt.Errorf("unzip seed corpus: %w", err)
		}

		// for each file in that directory, craft a new SeedMessage
		seeds, err := os.ReadDir(tmpDir)
		if err != nil {
			b.logger.Error("Failed to read seed corpus directory", zap.String("path", tmpDir), zap.Error(err))
			return fmt.Errorf("read seed corpus dir: %w", err)
		}

		seedCount := 0
		for _, seed := range seeds {
			if seed.IsDir() {
				continue
			}
			seedPath := filepath.Join(tmpDir, seed.Name())
			// craft a new SeedMessage
			seedChan <- types.SeedMessage{
				SeedFile: seedPath,
				Fuzzlet:  fakeFuzzlet,
			}
			seedCount++
		}

		totalSeeds += seedCount
	}

	b.logger.Info("Successfully discovered and sent seed corpus",
		zap.Int("total_seeds", totalSeeds),
		zap.Int("harnesses", len(seedZips)))

	return nil
}

// getDictionaryPath returns the absolute path to the dictionary file for the given harness.
// It first checks <harness>.options for a "dict = ..." entry, and validates its existence in the same directory.
// If not found or doesn't exist, it falls back to <harness>.dict.
func (b *TaskBuilder) getDictionaryPath(dir, harness string) (string, error) {
	optionsFile := filepath.Join(dir, harness+".options")
	dictFile := filepath.Join(dir, harness+".dict")
	autoDictFile := filepath.Join(dir, "b3yond.dict")

	// Check .options file
	if file, err := os.Open(optionsFile); err == nil {
		defer file.Close()

		var lastDict string
		scanner := bufio.NewScanner(file)
		for scanner.Scan() {
			line := scanner.Text()
			if strings.Contains(line, "dict") {
				if parts := strings.SplitN(line, "=", 2); len(parts) == 2 {
					key := strings.TrimSpace(parts[0])
					val := strings.TrimSpace(parts[1])
					if key == "dict" {
						lastDict = val
					}
				}
			}
		}
		if err := scanner.Err(); err == nil && lastDict != "" {
			absDict := filepath.Join(dir, lastDict)
			if stat, err := os.Stat(absDict); err == nil && !stat.IsDir() {
				return filepath.Abs(absDict)
			}
		}
	}

	// Fallback to harness.dict
	if stat, err := os.Stat(dictFile); err == nil && !stat.IsDir() {
		return filepath.Abs(dictFile)
	}

	// Finally, fallback to b3yond.dict (AFL++ auto dictionary generation)
	if stat, err := os.Stat(autoDictFile); err == nil && !stat.IsDir() {
		return filepath.Abs(autoDictFile)
	}

	return "", fmt.Errorf("no dictionary found for harness %s in directory %s", harness, dir)
}

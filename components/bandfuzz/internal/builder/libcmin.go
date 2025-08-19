package builder

import (
	"b3fuzz/internal/utils"
	"context"
	"fmt"
	"os"
	"path/filepath"

	"go.uber.org/zap"
)

const (
	// due to stupid historical reasons, we use the term "failed" to mean "finished"
	LibCminFinishedKey = "artifacts:%s:cmin:failed"
)

// For legacy projects, need to copy the libcmin.a as a "fuzzing engine" to the default library path.
// Add one line at the end of the Dockerfile to copy the `libcmin.a` to the default library path.
func (b *TaskBuilder) modifyDockerFileForCmin(dockerfilePath, libFuzzerEngineHostPath string) error {
	dockerfileContent, err := os.ReadFile(dockerfilePath)
	if err != nil {
		b.logger.Error("Failed to read Dockerfile", zap.String("path", dockerfilePath), zap.Error(err))
		return fmt.Errorf("failed to read Dockerfile: %w", err)
	}
	// Can't use absolute path in the Dockerfile
	// copy the libcmin.a to a relative path
	dockerfileLocationDir := filepath.Dir(dockerfilePath)
	utils.CopyFile(libFuzzerEngineHostPath, filepath.Join(dockerfileLocationDir, "libFuzzingEngine.a"))

	// Append the COPY command to the Dockerfile content
	copyCommand := "\nCOPY libFuzzingEngine.a /usr/lib/libFuzzingEngine.a\n"
	if err := os.WriteFile(dockerfilePath, append(dockerfileContent, []byte(copyCommand)...), 0644); err != nil {
		b.logger.Error("Failed to write modified Dockerfile", zap.String("path", dockerfilePath), zap.Error(err))
		return fmt.Errorf("failed to write modified Dockerfile: %w", err)
	}

	return nil
}

func (b *TaskBuilder) setCminFinishStatus(ctx context.Context, taskConfig TaskConfig) error {
	// set the finished key in Redis
	finishedKey := fmt.Sprintf(LibCminFinishedKey, taskConfig.TaskId)
	if err := b.redisClient.Set(ctx, finishedKey, "true", 0).Err(); err != nil {
		b.logger.Error("Failed to set libcmin finished key in Redis",
			zap.String("taskID", taskConfig.TaskId),
			zap.Error(err))
		return err
	}
	return nil
}

func (b *TaskBuilder) buildCminArtifacts(ctx context.Context, taskConfig TaskConfig, taskDetails *TaskDetails) error {
	libFuzzerEngineHostPath := filepath.Join(taskDetails.RepoPath, "libcmin.a")
	if err := utils.CopyFile(LibCminPath, libFuzzerEngineHostPath); err != nil {
		b.logger.Error("Failed to copy libcmin.a to project directory",
			zap.String("projectPath", taskDetails.RepoPath),
			zap.String("libFuzzerEngineHostPath", libFuzzerEngineHostPath),
			zap.Error(err))
	}

	dockerfilePath := filepath.Join(taskDetails.FuzzToolingPath, "projects", taskDetails.ProjectName, "Dockerfile")
	workdir, err := b.guessWorkDir(dockerfilePath)
	if err != nil {
		b.logger.Warn("Failed to guess workdir from Dockerfile", zap.String("path", dockerfilePath), zap.Error(err))
		workdir = filepath.Join("/src", taskConfig.ProjectName) // default to /src/<project name>
	}
	libFuzzingEngineDockerPath := filepath.Join(workdir, "libcmin.a")
	if err := b.modifyDockerFileForCmin(dockerfilePath, libFuzzerEngineHostPath); err != nil {
		b.logger.Error("Failed to modify Dockerfile for cmin build", zap.String("path", dockerfilePath), zap.Error(err))
		// but we can still continue the build process
	}

	cminBuildConfig := BuildConfig{
		"none",
		"none",
		map[string]string{
			"LIB_FUZZING_ENGINE": libFuzzingEngineDockerPath,
			"CFLAGS":             "-fsanitize=fuzzer-no-link",
			"CXXFLAGS":           "-fsanitize=fuzzer-no-link",
		},
	}

	artifacts, err := b.compile_with_retry(ctx, taskDetails, cminBuildConfig)
	if err != nil {
		b.logger.Error("Failed to compile cmin task", zap.Error(err))
		return fmt.Errorf("failed to compile cmin task: %w", err)
	}

	// transform the artifacts to just the harness name
	harnesses := make([]string, len(artifacts))
	for idx, artifact := range artifacts {
		harness := filepath.Base(artifact)
		harnesses[idx] = harness
	}

	// update the harnesses list in Redis for the task
	if err := b.updateHarnessList(ctx, harnesses, taskConfig.TaskId); err != nil {
		b.logger.Error("Failed to update harness list in Redis when building cmin artifacts",
			zap.String("taskID", taskConfig.TaskId),
			zap.Error(err))
	}

	for idx, harness := range harnesses {
		_, err := b.uploadArtifact(ctx, harness, taskConfig.TaskId, "none", "cmin", artifacts[idx])
		if err != nil {
			b.logger.Error("Failed to upload cmin artifacts",
				zap.String("taskID", taskConfig.TaskId),
				zap.Error(err))
			continue
		}
	}

	return nil
}

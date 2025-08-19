package builder

import (
	"b3fuzz/pkg/telemetry"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"go.uber.org/zap"
)

// download fetches the task according to the task config and prepares the runtime environment.
// It returns details about the downloaded task or an error if the download failed.
func (b *TaskBuilder) download(ctx context.Context, t TaskConfig) (*TaskDetails, error) {
	buildTracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	downloadTracer := buildTracer.Spawn("downloading task archives").WithAttributes(
		telemetry.EmptySpanAttributes(),
	)
	downloadTracer.Start()
	defer downloadTracer.End()

	downloadCtx := context.WithValue(ctx, telemetry.TracerKey{}, downloadTracer)

	b.logger.Info("Downloading task", zap.String("taskID", t.TaskId))

	// Create task directory
	taskDir := filepath.Join(b.localDir, t.TaskId)
	if err := os.MkdirAll(taskDir, 0755); err != nil {
		b.logger.Error("Failed to create task directory", zap.Error(err))
		return nil, fmt.Errorf("create task directory: %w", err)
	}

	// Extract fuzzing tooling
	fuzzToolingDir, err := b.extractArchive(downloadCtx, t.FuzzingTooling, taskDir, "fuzzing tooling")
	if err != nil {
		return nil, err
	}

	// Extract focus repository
	focusRepoDir, err := b.extractArchive(downloadCtx, t.Repo[0], taskDir, "focus repository")
	if err != nil {
		return nil, err
	}

	// Handle delta mode (apply patches)
	if t.TaskType == "delta" {
		if err := b.applyPatches(downloadCtx, t.Diff, taskDir, filepath.Join(taskDir, focusRepoDir)); err != nil {
			b.logger.Error("Failed to apply patches", zap.Error(err))
			return nil, err
		}
	}

	details := &TaskDetails{
		TaskID:          t.TaskId,
		FuzzToolingPath: filepath.Join(taskDir, fuzzToolingDir),
		RepoPath:        filepath.Join(taskDir, focusRepoDir),
		ProjectName:     t.ProjectName,
	}

	// Store the details in the map
	b.taskDetails[t.TaskId] = details

	return details, nil
}

// extractArchive extracts a tar.gz archive to the specified directory and returns the top-level directory name.
func (b *TaskBuilder) extractArchive(ctx context.Context, archivePath, destDir, archiveType string) (string, error) {
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	extractTracer := tracer.Spawn("extracting archive").WithAttributes(
		telemetry.EmptySpanAttributes().
			WithExtraAttribute("archivePath", archivePath).
			WithExtraAttribute("archiveType", archiveType),
	)
	extractTracer.Start()
	defer extractTracer.End()

	// Get the top-level directory name from the archive
	topLevelDir, err := b.getTopLevelDirFromTar(ctx, archivePath)
	if err != nil {
		b.logger.Error("Failed to get directory name from archive",
			zap.String("type", archiveType),
			zap.Error(err))
		return "", fmt.Errorf("get directory from %s archive: %w", archiveType, err)
	}

	// Extract the archive
	cmd := exec.CommandContext(ctx, "tar", "-xzf", archivePath, "-C", destDir)
	if err := cmd.Run(); err != nil {
		b.logger.Error("Failed to extract archive",
			zap.String("type", archiveType),
			zap.String("path", archivePath),
			zap.Error(err))
		return "", fmt.Errorf("extract %s archive: %w", archiveType, err)
	}

	return topLevelDir, nil
}

// applyPatches extracts and applies patches from a diff archive to the focus repository.
func (b *TaskBuilder) applyPatches(ctx context.Context, diffArchive, taskDir, focusDir string) error {
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	diffTracer := tracer.Spawn("applying diff").WithAttributes(
		telemetry.EmptySpanAttributes().
			WithExtraAttribute("diffArchive", diffArchive).
			WithExtraAttribute("taskDir", taskDir).
			WithExtraAttribute("focusDir", focusDir),
	)
	diffTracer.Start()
	defer diffTracer.End()

	// Extract the diff archive
	diffDir, err := b.extractArchive(ctx, diffArchive, taskDir, "diff")
	if err != nil {
		return err
	}

	diffPath := filepath.Join(taskDir, diffDir)

	// Check if the diff path exists and determine if it's a file or directory
	fileInfo, err := os.Stat(diffPath)
	if err != nil {
		b.logger.Error("Invalid diff path", zap.String("path", diffPath), zap.Error(err))
		return fmt.Errorf("stat diff path: %w", err)
	}

	if !fileInfo.IsDir() {
		// Single patch file case
		if err := b.applyPatchFile(ctx, diffPath, focusDir); err != nil {
			return err
		}
	} else {
		// Directory with multiple patch files
		if err := b.applyPatchesFromDir(ctx, diffPath, focusDir); err != nil {
			return err
		}
	}

	return nil
}

// applyPatchFile applies a single patch file to the focus repository.
func (b *TaskBuilder) applyPatchFile(ctx context.Context, patchPath, focusDir string) error {
	// Only process .patch or .diff files
	ext := filepath.Ext(patchPath)
	if ext != ".patch" && ext != ".diff" {
		return nil // Not a patch file, nothing to do
	}

	b.logger.Debug("Applying patch file", zap.String("path", patchPath))

	patchFile, err := os.Open(patchPath)
	if err != nil {
		b.logger.Error("Failed to open patch file", zap.String("path", patchPath), zap.Error(err))
		return fmt.Errorf("open patch file: %w", err)
	}
	defer patchFile.Close()

	cmd := exec.CommandContext(ctx, "patch", "--batch", "--no-backup-if-mismatch", "-p1")
	cmd.Dir = focusDir
	cmd.Stdin = patchFile

	if err := cmd.Run(); err != nil {
		b.logger.Error("Failed to apply patch", zap.String("path", patchPath), zap.Error(err))
		return fmt.Errorf("apply patch: %w", err)
	}

	b.logger.Info("Applied patch file", zap.String("path", patchPath))
	return nil
}

// applyPatchesFromDir applies all patch files from a directory to the focus repository.
func (b *TaskBuilder) applyPatchesFromDir(ctx context.Context, patchDir, focusDir string) error {
	files, err := os.ReadDir(patchDir)
	if err != nil {
		b.logger.Error("Failed to read diff directory", zap.String("path", patchDir), zap.Error(err))
		return fmt.Errorf("read diff directory: %w", err)
	}

	for _, file := range files {
		patchPath := filepath.Join(patchDir, file.Name())

		// Skip non-patch files
		ext := filepath.Ext(file.Name())
		if ext != ".patch" && ext != ".diff" {
			continue
		}

		if err := b.applyPatchFile(ctx, patchPath, focusDir); err != nil {
			// Log error but continue with other patches
			b.logger.Warn("Failed to apply patch, continuing with others",
				zap.String("path", patchPath),
				zap.Error(err))
		}
	}

	return nil
}

// getTopLevelDirFromTar extracts the name of the top-level directory from a tar.gz file.
// This optimized version assumes the tar.gz has exactly one top-level directory.
func (b *TaskBuilder) getTopLevelDirFromTar(ctx context.Context, tarPath string) (string, error) {
	// Use -t to list contents, but only get the first entry to improve performance
	cmd := exec.CommandContext(ctx, "tar", "-tzf", tarPath)
	b.logger.Debug("Running tar -tzf command", zap.String("command", cmd.String()))
	output, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("list tar contents: %w", err)
	}

	// Get the first line only
	firstLine := strings.TrimSpace(strings.Split(string(output), "\n")[0])
	if firstLine == "" {
		return "", fmt.Errorf("no files found in archive")
	}

	// Remove any trailing slash if it's a directory
	firstLine = strings.TrimRight(firstLine, "/")

	// Handle case where directory might be prefixed with "./"
	firstLine = strings.TrimPrefix(firstLine, "./")
	b.logger.Debug("Top level dir", zap.String("dir", firstLine))
	return firstLine, nil
}

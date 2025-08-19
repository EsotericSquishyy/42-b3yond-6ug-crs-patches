package builder

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"go.uber.org/zap"
)

// guess the workdir from the Dockerfile
func (b *TaskBuilder) guessWorkDir(dockerfilePath string) (string, error) {
	dockerfile, err := os.ReadFile(dockerfilePath)
	if err != nil {
		b.logger.Error("Failed to read Dockerfile", zap.String("path", dockerfilePath), zap.Error(err))
		return "", fmt.Errorf("failed to read Dockerfile: %w", err)
	}

	re := regexp.MustCompile(`(?im)^\s*WORKDIR\s+([^\s]+)`)
	matches := re.FindAllSubmatch(dockerfile, -1)
	if len(matches) == 0 {
		return "", fmt.Errorf("WORKDIR not found in Dockerfile")
	}
	workdir := string(matches[len(matches)-1][1])
	workdir = strings.ReplaceAll(workdir, "$SRC", "/src")

	// if workdir is not absolute, we add /src to it
	if !strings.HasPrefix(workdir, "/") {
		workdir = filepath.Join("/src", workdir)
	}
	return workdir, nil
}

// get rid of all environment variables that are related to OpenTelemetry
func filterOtelEnv(env []string) []string {
	var filtered []string
	for _, e := range env {
		if strings.HasPrefix(e, "OTEL_") || strings.HasPrefix(e, "OTLP_") {
			continue // Skip OpenTelemetry related environment variables
		}
		filtered = append(filtered, e)
	}
	return filtered
}

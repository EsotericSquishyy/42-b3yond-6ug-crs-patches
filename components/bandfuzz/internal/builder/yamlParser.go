package builder

import (
	"context"
	"os"
	"path/filepath"

	"go.uber.org/zap"
	"gopkg.in/yaml.v3"
)

type ProjectYaml struct {
	Language   string   `yaml:"language"`
	Sanitizers []string `yaml:"sanitizers"`
}

func (b *TaskBuilder) GetProjectYaml(ctx context.Context, details TaskDetails) (*ProjectYaml, error) {
	// try to parse <fuzz tooling>/projects/<project name>/project.yaml
	projectYamlPath := filepath.Join(details.FuzzToolingPath, "projects", details.ProjectName, "project.yaml")
	projectYamlContent, err := os.ReadFile(projectYamlPath)
	if err != nil {
		b.logger.Error("Failed to read project.yaml", zap.String("taskID", details.TaskID), zap.Error(err))
		return nil, err
	}

	var projectYaml ProjectYaml
	if err := yaml.Unmarshal(projectYamlContent, &projectYaml); err != nil {
		b.logger.Error("Failed to parse project.yaml", zap.String("taskID", details.TaskID), zap.Error(err))
		return nil, err
	}

	return &projectYaml, nil
}

func (b *TaskBuilder) GetProjectLanguage(ctx context.Context, d TaskDetails) (string, error) {
	project, err := b.GetProjectYaml(ctx, d)
	if err != nil {
		return "", err
	}
	return project.Language, nil
}

func (b *TaskBuilder) GetSupportedSanitizers(ctx context.Context, d TaskDetails) ([]string, error) {
	project, err := b.GetProjectYaml(ctx, d)
	if err != nil {
		return nil, err
	}
	return project.Sanitizers, nil
}

package builder

import (
	"context"
	"path/filepath"

	"go.uber.org/zap"
)

func (b *TaskBuilder) buildAflArtifacts(ctx context.Context, taskConfig TaskConfig, taskDetails *TaskDetails) error {
	// Get supported sanitizers from project.yaml
	supportedSanitizers, err := b.GetSupportedSanitizers(ctx, *taskDetails)
	if err != nil {
		b.logger.Warn("Failed to get supported sanitizers, using default 'address'", zap.Error(err))
		supportedSanitizers = []string{"address"} // Default if not specified or error
	}
	if len(supportedSanitizers) == 0 {
		b.logger.Warn("No sanitizers specified in project.yaml, using default 'address'")
		supportedSanitizers = []string{"address"} // Default if empty list
	}

	b.logger.Info("Building for sanitizers", zap.Strings("sanitizers", supportedSanitizers))

	fuzzEngine := "afl"

	for _, sanitizer := range supportedSanitizers {
		isolatedDetails := taskDetails.clone()

		buildConfig := BuildConfig{
			sanitizer,
			fuzzEngine,
			map[string]string{
				"AFL_LLVM_DICT2FILE":         "/out/b3yond.dict", // use AFL++ automatic dictionary generation
				"AFL_LLVM_DICT2FILE_NO_MAIN": "1",                // disable main function in dictionary generation
			},
		}

		artifacts, err := b.compile_with_retry(ctx, isolatedDetails, buildConfig)
		if err != nil {
			b.logger.Error("Failed to compile task for sanitizer",
				zap.String("taskID", taskConfig.TaskId),
				zap.String("sanitizer", sanitizer),
				zap.Error(err))
			continue
		}
		if err := b.discoverFuzzCorpus(isolatedDetails); err != nil {
			b.logger.Error("Failed to found seed corpus files",
				zap.String("project", isolatedDetails.ProjectName))
		}

		b.logger.Info("Task compiled successfully for sanitizer",
			zap.String("taskID", taskConfig.TaskId),
			zap.String("sanitizer", sanitizer),
			zap.Strings("artifacts", artifacts))

		// transform the artifacts to just the harness name
		harnesses := make([]string, len(artifacts))
		for idx, artifact := range artifacts {
			harness := filepath.Base(artifact)
			harnesses[idx] = harness
		}

		// update the harnesses list in Redis for the task
		if err := b.updateHarnessList(ctx, harnesses, taskConfig.TaskId); err != nil {
			b.logger.Error("Failed to update harness list in Redis",
				zap.String("taskID", taskConfig.TaskId),
				zap.String("sanitizer", sanitizer),
				zap.Error(err))
			continue
		}

		// dict
		for _, artifact := range artifacts {
			outDir := filepath.Dir(artifact)
			harness := filepath.Base(artifact)
			if dictPath, err := b.getDictionaryPath(outDir, harness); err == nil {
				b.uploadDict(ctx, harness, taskConfig.TaskId, dictPath)
			} else {
				b.logger.Warn("Failed to get dictionary path for harness, skipped",
					zap.String("taskID", taskConfig.TaskId),
					zap.String("sanitizer", sanitizer),
					zap.String("harness", harness),
					zap.Error(err))
			}
		}

		for idx, harness := range harnesses {
			uploadPath, err := b.uploadArtifact(ctx, harness, taskConfig.TaskId, sanitizer, fuzzEngine, artifacts[idx])
			if err != nil {
				b.logger.Error("Failed to upload artifacts for sanitizer",
					zap.String("taskID", taskConfig.TaskId),
					zap.String("sanitizer", sanitizer),
					zap.Error(err))
				continue
			}
			if err := b.addFuzzlet(ctx, taskConfig.TaskId, harness, sanitizer, fuzzEngine, uploadPath); err != nil {
				b.logger.Error("Failed to add fuzzlet to Redis",
					zap.String("taskID", taskConfig.TaskId),
					zap.String("sanitizer", sanitizer),
					zap.Error(err))
				continue
			}
		}

		b.logger.Info("Artifacts uploaded successfully for sanitizer",
			zap.String("taskID", taskConfig.TaskId),
			zap.String("sanitizer", sanitizer))
	}

	return nil
}

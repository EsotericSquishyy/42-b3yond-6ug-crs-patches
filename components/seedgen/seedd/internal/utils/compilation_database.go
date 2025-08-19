package utils

import (
	"BugBuster/SeedD/internal/logging"
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"go.uber.org/zap"
)

// ConstructCompilationDatabase combines every JSON line from files in
// /out/compilation_database into one JSON array in /out/compile_commands/compile_commands.json
// without parsing each line as JSON. Returns the folder path where the file was created.
func ConstructCompilationDatabase() (string, error) {
	logger := logging.Logger

	compilationDir := filepath.Join("/", "out", "compilation_database")
	outFolder := filepath.Join("/", "out", "compile_commands")
	outFilePath := filepath.Join(outFolder, "compile_commands.json")

	// Create the output directory if it doesn't exist
	if err := os.MkdirAll(outFolder, 0755); err != nil {
		logger.Error("failed to create output directory %s: %w", zap.String("outFolder", outFolder), zap.Error(err))
		return "", fmt.Errorf("failed to create output directory %s: %w", outFolder, err)
	}

	// List all files in /out/compilation_database
	files, err := os.ReadDir(compilationDir)
	if err != nil {
		logger.Error("failed to read directory %s: %w", zap.String("compilationDir", compilationDir), zap.Error(err))
		return "", fmt.Errorf("failed to read directory %s: %w", compilationDir, err)
	}

	// Create (or overwrite) the final file
	outFile, err := os.Create(outFilePath)
	if err != nil {
		return "", fmt.Errorf("failed to create output file %s: %w", outFilePath, err)
	}
	defer func() {
		if cerr := outFile.Close(); cerr != nil {
			logger.Error("warning: failed to close output file %s: %v", zap.String("outFilePath", outFilePath), zap.Error(cerr))
		}
	}()

	// Write the opening bracket of the JSON array
	if _, err := outFile.WriteString("[\n"); err != nil {
		logger.Error("failed to write to output file: %w", zap.Error(err))
		return "", fmt.Errorf("failed to write to output file: %w", err)
	}

	firstObject := true
	for _, file := range files {
		// Skip folders and non-.json files
		if file.IsDir() || filepath.Ext(file.Name()) != ".json" {
			continue
		}

		filePath := filepath.Join(compilationDir, file.Name())
		f, err := os.Open(filePath)
		if err != nil {
			return "", fmt.Errorf("failed to open file %s: %w", filePath, err)
		}

		scanner := bufio.NewScanner(f)
		for scanner.Scan() {
			line := scanner.Text()
			// Remove trailing comma (the assumption is that each line ends with ,)
			trimmed := strings.TrimRight(line, ", \t\r\n")

			// If we already wrote one object, add a comma separator
			// before the next object
			if !firstObject {
				if _, err := outFile.WriteString(",\n"); err != nil {
					logger.Error("failed to write to output file: %w", zap.Error(err))
					_ = f.Close()
					return "", err
				}
			}
			firstObject = false

			// Write the trimmed line (still a valid JSON object if we removed its trailing comma)
			if _, err := outFile.WriteString(trimmed); err != nil {
				logger.Error("failed to write to output file: %w", zap.Error(err))
				_ = f.Close()
				return "", err
			}
		}

		if err := scanner.Err(); err != nil {
			logger.Error("error reading file %s: %w", zap.String("filePath", filePath), zap.Error(err))
			_ = f.Close()
			return "", fmt.Errorf("error reading file %s: %w", filePath, err)
		}

		if err := f.Close(); err != nil {
			logger.Error("failed to close file %s: %w", zap.String("filePath", filePath), zap.Error(err))
			return "", fmt.Errorf("failed to close file %s: %w", filePath, err)
		}
	}

	// Close the JSON array
	if _, err := outFile.WriteString("\n]\n"); err != nil {
		return "", fmt.Errorf("failed to write closing bracket to output file: %w", err)
	}

	logger.Info("Successfully created %s", zap.String("outFilePath", outFilePath))
	return outFolder, nil
}

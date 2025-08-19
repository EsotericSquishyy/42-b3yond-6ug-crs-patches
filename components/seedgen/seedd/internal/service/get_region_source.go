package service

import (
	"BugBuster/SeedD/internal/logging"
	"BugBuster/SeedD/internal/runtime"
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"unicode/utf8"

	"go.uber.org/zap"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func GetRegionSource(ctx context.Context, req *runtime.GetRegionSourceRequest) (*runtime.GetRegionSourceResponse, error) {
	logger := logging.Logger.With(
		zap.String("filepath", req.Filepath),
		zap.Uint64("start_line", req.StartLine),
		zap.Uint64("end_line", req.EndLine),
	)

	if err := validatePath(req.Filepath); err != nil {
		logger.Error("Error validating path",
			zap.String("filepath", req.Filepath),
			zap.Error(err),
		)
		return nil, status.Error(codes.NotFound, err.Error())
	}

	// If no positions provided, use 0 values to indicate whole file should be returned
	if req.StartLine == 0 && req.StartColumn == 0 && req.EndLine == 0 && req.EndColumn == 0 {
		content, err := os.ReadFile(req.Filepath)
		if err != nil {
			logger.Error("Error reading file",
				zap.String("filepath", req.Filepath),
				zap.Error(err),
			)
			return nil, status.Error(codes.Internal, err.Error())
		}
		return &runtime.GetRegionSourceResponse{
			Source: string(content),
		}, nil
	}

	source, err := getRegionSource(req.Filepath, req.StartLine, req.StartColumn, req.EndLine, req.EndColumn)
	if err != nil {
		logger.Error("Error getting region source",
			zap.String("filepath", req.Filepath),
			zap.Error(err),
		)
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &runtime.GetRegionSourceResponse{
		Source: source,
	}, nil
}

func validatePath(filepath string) error {
	if _, err := os.Stat(filepath); os.IsNotExist(err) {
		return fmt.Errorf("file not found at path: %s", filepath)
	}
	return nil
}

func getRegionSource(filepath string, startLine, startColumn, endLine, endColumn uint64) (string, error) {
	content, err := os.ReadFile(filepath)
	if err != nil {
		return "", fmt.Errorf("failed to read file: %v", err)
	}

	lines := strings.Split(string(content), "\n")
	totalLines := uint64(len(lines))

	log.Printf("File %s has %d lines", filepath, totalLines)

	// Validate line numbers
	if startLine == 0 || endLine == 0 || startLine > totalLines || endLine > totalLines || startLine > endLine {
		return "", fmt.Errorf("invalid line range")
	}

	var resultLines []string

	for i := startLine - 1; i < endLine; i++ {
		line := lines[i]
		lineLength := uint64(utf8.RuneCountInString(line))

		// Determine start and end columns for the current line
		var lineStartCol, lineEndCol uint64

		if i == startLine-1 {
			lineStartCol = startColumn - 1 // Convert to 0-based index
			if lineStartCol > lineLength {
				return "", fmt.Errorf("start column %d exceeds line length", startColumn)
			}
		} else {
			lineStartCol = 0
		}

		if i == endLine-1 {
			lineEndCol = endColumn - 1 // endColumn is exclusive
			if lineEndCol > lineLength {
				return "", fmt.Errorf("end column %d exceeds line length", endColumn)
			}
		} else {
			lineEndCol = lineLength
		}

		// Extract substring using rune slicing for Unicode support
		runes := []rune(line)
		lineFragment := string(runes[lineStartCol:lineEndCol])
		resultLines = append(resultLines, lineFragment)
	}

	// Join the lines with newlines
	result := strings.Join(resultLines, "\n")

	if result == "" {
		return "", fmt.Errorf("no content found between lines %d and %d", startLine, endLine)
	}

	return result, nil
}

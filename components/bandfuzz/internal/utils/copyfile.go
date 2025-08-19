package utils

import (
	"fmt"
	"io"
	"os"
	"os/exec"
)

// CopyFile copies a file from src to dst. If dst exists, it will be overwritten.
// It returns an error if the operation fails.
func CopyFile(src, dst string) error {
	source, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("failed to open source file: %w", err)
	}
	defer func() {
		if cerr := source.Close(); cerr != nil {
			err = fmt.Errorf("failed to close source file: %w", cerr)
		}
	}()

	sourceInfo, err := source.Stat()
	if err != nil {
		return fmt.Errorf("failed to stat source file: %w", err)
	}

	// Remove destination file if it exists
	if err := os.Remove(dst); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("failed to remove existing destination file: %w", err)
	}
	destination, err := os.OpenFile(dst, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, sourceInfo.Mode())
	if err != nil {
		return fmt.Errorf("failed to create destination file: %w", err)
	}
	defer func() {
		if cerr := destination.Close(); cerr != nil {
			err = fmt.Errorf("failed to close destination file: %w", cerr)
		}
	}()

	bytesCopied, err := io.Copy(destination, source)
	if err != nil {
		return fmt.Errorf("failed to copy file contents: %w", err)
	}

	if bytesCopied != sourceInfo.Size() {
		return fmt.Errorf("incomplete copy: expected %d bytes, got %d bytes", sourceInfo.Size(), bytesCopied)
	}

	return nil
}

func CopyDir(src, dst string) error {
	// Check if the source directory exists
	if _, err := os.Stat(src); os.IsNotExist(err) {
		return fmt.Errorf("source directory does not exist: %w", err)
	}
	cmd := exec.Command("cp", "-r", src+"/.", dst)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to copy directory: %w", err)
	}
	// Check if the destination directory exists
	if _, err := os.Stat(dst); os.IsNotExist(err) {
		return fmt.Errorf("destination directory does not exist after copy: %w", err)
	}
	return nil
}

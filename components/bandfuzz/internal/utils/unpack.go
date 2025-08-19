package utils

import (
	"fmt"
	"net/http"
	"os"
	"os/exec"
)

// Unpack tar file to destination folder
func UnpackTar(tarFile string, dstFolder string) error {
	cmd := exec.Command("tar", "-xf", tarFile, "-C", dstFolder)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to unpack tar file: %w", err)
	}
	return nil
}

func UnpackTarGz(tarGzFile string, dstFolder string) error {
	cmd := exec.Command("tar", "-xzf", tarGzFile, "-C", dstFolder)
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to unpack tar.gz file: %w", err)
	}
	return nil
}

func IsTarGz(file string) bool {
	fileHandle, err := os.Open(file)
	if err != nil {
		return false
	}
	defer fileHandle.Close()

	buffer := make([]byte, 512) // Read the first 512 bytes for MIME detection
	_, err = fileHandle.Read(buffer)
	if err != nil {
		return false
	}

	mimeType := http.DetectContentType(buffer)
	return mimeType == "application/gzip"
}

func CompressTarGz(srcFolder, tarGzFile string) error {
	cmd := exec.Command("tar", "-czf", tarGzFile, "-C", srcFolder, ".")
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to create tar.gz file: %w", err)
	}
	return nil
}

func Unzip(zipFile, dstFolder string) error {
	cmd := exec.Command("unzip", zipFile, "-d", dstFolder)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to unzip file: %w", err)
	}
	return nil
}

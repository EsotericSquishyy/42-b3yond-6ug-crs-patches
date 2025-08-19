package corpus

import (
	"crypto/rand"
	"fmt"
	"os"
	"os/exec"
	"path"
)

type RandomSeedGrabber struct{}

func NewRandomSeedGrabber() *RandomSeedGrabber {
	return &RandomSeedGrabber{}
}

func generateRandomSeeds(taskId, harness string) (string, error) {
	seedFolder := path.Join("/tmp/b3fuzz/fakeseeds", taskId, harness)
	tarFilePath := path.Join("/tmp/b3fuzz/fakeseeds", fmt.Sprintf("%s_%s_seeds.tar.gz", taskId, harness))

	// Create the seed folder
	if err := os.MkdirAll(seedFolder, 0755); err != nil {
		return "", err
	}

	// Generate random seed files
	for i := range 30 {
		seedFilePath := path.Join(seedFolder, fmt.Sprintf("seed%d.bin", i))
		seedData := make([]byte, 1024) // 1KB random data
		if _, err := rand.Read(seedData); err != nil {
			return "", err
		}
		if err := os.WriteFile(seedFilePath, seedData, 0644); err != nil {
			return "", err
		}
	}

	// Create a tar file containing the seeds
	cmd := exec.Command("tar", "-czf", tarFilePath, "-C", seedFolder, ".")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("failed to create tar file: %w", err)
	}

	return tarFilePath, nil
}

func (s *RandomSeedGrabber) GrabCorpusBlob(taskId, harness string) (string, error) {
	// Generate fake seeds and return the path to the tar file
	return generateRandomSeeds(taskId, harness)
}

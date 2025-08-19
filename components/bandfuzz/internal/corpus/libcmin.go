package corpus

import (
	"b3fuzz/config"
	"errors"
	"fmt"
	"io"
	"net/http"

	"go.uber.org/fx"
	"go.uber.org/zap"
)

type LibCminCorpusGrabber struct {
	logger    *zap.Logger
	appConfig *config.AppConfig
}

func NewLibCminCorpusGrabber(logger *zap.Logger, appConfig *config.AppConfig, lifeCycle fx.Lifecycle) *LibCminCorpusGrabber {
	return &LibCminCorpusGrabber{
		logger,
		appConfig,
	}
}

// GetSeedsFromRedis retrieves corpus blob from libcmin server
func (s *LibCminCorpusGrabber) GrabCorpusBlob(taskId, harness string) (string, error) {
	libCminHost := s.appConfig.LibCminHost
	if libCminHost == "" {
		return "", errors.New("LibCmin host is not set")
	}

	endpoint := fmt.Sprintf("http://%s/cmin/%s/%s", libCminHost, taskId, harness)
	resp, err := http.Get(endpoint)
	if err != nil {
		s.logger.Error("Failed to get corpus blob", zap.Error(err))
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		s.logger.Error("Failed to get corpus blob", zap.String("status", resp.Status))
		return "", fmt.Errorf("failed to get corpus blob: %s", resp.Status)
	}

	// the response should be returned (as a string)
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		s.logger.Error("Failed to read response body", zap.Error(err))
		return "", err
	}

	return string(body), nil
}

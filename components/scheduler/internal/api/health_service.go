package api

import (
	"crs-scheduler/config"
	"crs-scheduler/models"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync/atomic"
	"time"

	"go.uber.org/fx"
	"go.uber.org/zap"
	"gorm.io/gorm"
)

const (
	// RetryInterval is the time to wait between health check attempts
	RetryInterval = time.Second
)

// HealthService manages the health status of the application and its dependencies.
type HealthService struct {
	ready int32 // 0 - not ready, 1 - ready for one requirement, 2 - ready for all requirements
	db    *gorm.DB
}

type HealthServiceParams struct {
	fx.In
	DB     *gorm.DB
	Logger *zap.Logger
}

// NewHealthService creates a new HealthService instance.
func NewHealthService(params HealthServiceParams) *HealthService {
	return &HealthService{
		ready: 0,
		db:    params.DB,
	}
}

// IsReady returns true if all health check requirements are met.
func (h *HealthService) IsReady() bool {
	return atomic.LoadInt32(&h.ready) == 2
}

// incrementReady increments the ready counter atomically.
func (h *HealthService) incrementReady() {
	atomic.AddInt32(&h.ready, 1)
}

// PingResponse represents the response from a ping endpoint.
type PingResponse struct {
	Status  string `json:"status,omitempty"`
	Message string `json:"message,omitempty"`
}

// createCrsUser ensures the CRS user exists in the database with the correct credentials.
func (h *HealthService) createCrsUser(logger *zap.Logger, config *config.AppConfig) error {
	user := models.User{
		Username: config.CrsAPI.Username,
		Password: config.CrsAPI.Password,
	}

	var existingUser models.User
	result := h.db.Where("username = ?", user.Username).First(&existingUser)

	switch result.Error {
	case gorm.ErrRecordNotFound:
		if result := h.db.Create(&user); result.Error != nil {
			logger.Error("failed to create CRS user", zap.Error(result.Error))
			return fmt.Errorf("failed to create CRS user: %w", result.Error)
		}
	case nil:
		if result := h.db.Model(&existingUser).Update("password", user.Password); result.Error != nil {
			logger.Error("failed to update CRS user password", zap.Error(result.Error))
			return fmt.Errorf("failed to update CRS user password: %w", result.Error)
		}
	default:
		logger.Error("database error when checking for CRS user", zap.Error(result.Error))
		return fmt.Errorf("database error when checking for CRS user: %w", result.Error)
	}

	h.incrementReady()
	logger.Info("CRS user created successfully")
	return nil
}

// waitForCompetitionAPI polls the competition API until it's ready.
func (h *HealthService) waitForCompetitionAPI(logger *zap.Logger, config *config.AppConfig) error {
	competitionAPI := config.CompetitionAPI
	pingEndpoint := competitionAPI.URL + "/v1/ping"

	for {
		req, err := http.NewRequest(http.MethodGet, pingEndpoint, nil)
		if err != nil {
			logger.Error("failed to create request", zap.Error(err))
			time.Sleep(RetryInterval)
			continue
		}

		req.SetBasicAuth(competitionAPI.Username, competitionAPI.Password)

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			logger.Error("failed to send request", zap.Error(err))
			time.Sleep(RetryInterval)
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return fmt.Errorf("failed to read response body: %w", err)
		}

		var pingResp PingResponse
		if err := json.Unmarshal(body, &pingResp); err != nil {
			return fmt.Errorf("failed to decode response: %w, body: %s", err, string(body))
		}

		if resp.StatusCode == http.StatusOK && pingResp.Status == "ready" {
			h.incrementReady()
			return nil
		}

		if pingResp.Message == "Unauthorized" || resp.StatusCode != http.StatusOK {
			return fmt.Errorf("competition API returned error: status=%d, message=%s, body=%s",
				resp.StatusCode, pingResp.Message, string(body))
		}

		logger.Info("competition API is not ready, retrying", zap.Duration("interval", RetryInterval))
		time.Sleep(RetryInterval)
	}
}

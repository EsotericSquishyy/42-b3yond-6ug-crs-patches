package api

import (
	"crs-scheduler/models"
	"fmt"

	"go.uber.org/fx"
	"gorm.io/gorm"
)

// StatusService manages the status information of the application.
type StatusService struct {
	db *gorm.DB
}

type StatusServiceParams struct {
	fx.In
	DB *gorm.DB
}

// NewStatusService creates a new StatusService instance.
func NewStatusService(params StatusServiceParams) *StatusService {
	return &StatusService{
		db: params.DB,
	}
}

// GetTaskCount returns the number of tasks that are in processing or waiting state
func (s *StatusService) GetTaskCount() (int64, error) {
	var count int64
	result := s.db.Model(&models.Task{}).
		Where("status IN ?", []string{"processing", "waiting"}).
		Count(&count)
	if result.Error != nil {
		return 0, fmt.Errorf("failed to get task count: %w", result.Error)
	}
	return count, nil
}

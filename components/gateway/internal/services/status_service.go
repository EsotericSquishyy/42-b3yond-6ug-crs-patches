package services

import (
	"crs-gateway/internal/db"
	"time"

	"gorm.io/gorm"
)

type StatusService interface {
	GetTaskStatus() (map[db.TaskStatusEnum]int64, error)
	GetLastClearTime() time.Time
	ClearStatus() error
}

type StatusServiceImpl struct {
	db *gorm.DB

	// internal states
	lastClearTime time.Time
}

func NewStatusService(db *gorm.DB) StatusService {
	return &StatusServiceImpl{
		db:            db,
		lastClearTime: time.Now(),
	}
}

// StatusCount represents the count of tasks for each status
type StatusCount struct {
	Status db.TaskStatusEnum `gorm:"column:status"`
	Count  int               `gorm:"column:count"`
}

// GetTaskStatus returns the count of tasks grouped by status
func (s *StatusServiceImpl) GetTaskStatus() (map[db.TaskStatusEnum]int64, error) {
	var results []StatusCount

	if err := s.db.Model(&db.Task{}).
		Select("status, COUNT(*) as count").
		Where("created_at > ?", s.lastClearTime).
		Group("status").
		Find(&results).Error; err != nil {
		return nil, err
	}

	// Convert to map
	statusCount := make(map[db.TaskStatusEnum]int64)
	for _, result := range results {
		statusCount[result.Status] = int64(result.Count)
	}

	return statusCount, nil
}

func (s *StatusServiceImpl) GetLastClearTime() time.Time {
	return s.lastClearTime
}

func (s *StatusServiceImpl) ClearStatus() error {
	s.lastClearTime = time.Now()
	return nil
}

package database

import (
	"context"
	"time"

	"gorm.io/gorm"
)

// inserts multiple bug records into the database
func AddBugs(ctx context.Context, db *gorm.DB, bugs []*Bug) error {
	if len(bugs) == 0 {
		return nil
	}
	return db.WithContext(ctx).Create(bugs).Error
}

// NewBug creates a new Bug object with the provided parameters
func NewBug(
	taskID string,
	poc string,
	harnessName string,
	sanitizer string,
) *Bug {
	return &Bug{
		TaskID:       taskID,
		CreatedAt:    time.Now(),
		Architecture: "x86_64",
		POC:          poc,
		HarnessName:  harnessName,
		Sanitizer:    sanitizer,
	}
}

// inserts a single seed record into the database
func AddSeed(ctx context.Context, db *gorm.DB, seed *Seed) error {
	if seed == nil {
		return nil
	}
	return db.WithContext(ctx).Create(seed).Error
}

// NewSeed creates a new Seed object with the provided parameters
func NewSeed(
	taskID string,
	path string,
	harnessName string,
	fuzzer FuzzerTypeEnum,
	instance string,
	coverage float64,
	metric Metric,
) *Seed {
	return &Seed{
		TaskID:      taskID,
		CreatedAt:   time.Now(),
		Path:        path,
		HarnessName: harnessName,
		Fuzzer:      fuzzer,
		Instance:    instance,
		Coverage:    coverage,
		Metric:      metric,
	}
}

package database

import (
	"database/sql/driver"
	"encoding/json"
	"errors"
	"time"
)

// FuzzerTypeEnum represents the fuzzer type enum in the database
type FuzzerTypeEnum string

const (
	SeedGen       FuzzerTypeEnum = "seedgen"
	PrimeFuzz     FuzzerTypeEnum = "prime"
	GeneralFuzz   FuzzerTypeEnum = "general"
	DirectedFuzz  FuzzerTypeEnum = "directed"
	CorpusGrabber FuzzerTypeEnum = "corpus"
)

// Seed represents a record in the public.seeds table
type Seed struct {
	ID          int            `gorm:"primaryKey;column:id"`
	TaskID      string         `gorm:"column:task_id;not null"`
	CreatedAt   time.Time      `gorm:"column:created_at;default:now()"`
	Path        string         `gorm:"column:path"`
	HarnessName string         `gorm:"column:harness_name"`
	Fuzzer      FuzzerTypeEnum `gorm:"column:fuzzer"`
	Instance    string         `gorm:"column:instance"`
	Coverage    float64        `gorm:"column:coverage"`
	Metric      Metric         `gorm:"column:metric;type:jsonb"`
}

// Bug represents a record in the public.bugs table
type Bug struct {
	ID           int             `gorm:"primaryKey;column:id"`
	TaskID       string          `gorm:"column:task_id;not null"`
	CreatedAt    time.Time       `gorm:"column:created_at;default:now()"`
	Architecture string          `gorm:"column:architecture;not null"`
	POC          string          `gorm:"column:poc;not null"`
	HarnessName  string          `gorm:"column:harness_name;not null"`
	Sanitizer    string          `gorm:"column:sanitizer;not null"`
	SarifReport  json.RawMessage `gorm:"column:sarif_report;type:jsonb"`
}

// Metric represents the jsonb field in the seeds table
type Metric map[string]any

// Value implements the driver.Valuer interface for the Metric type
func (m Metric) Value() (driver.Value, error) {
	if m == nil {
		return nil, nil
	}
	return json.Marshal(m)
}

// Scan implements the sql.Scanner interface for the Metric type
func (m *Metric) Scan(value any) error {
	if value == nil {
		*m = nil
		return nil
	}

	bytes, ok := value.([]byte)
	if !ok {
		return errors.New("type assertion to []byte failed")
	}

	return json.Unmarshal(bytes, &m)
}

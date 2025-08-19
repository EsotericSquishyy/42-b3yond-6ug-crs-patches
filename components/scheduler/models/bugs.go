package models

import (
	"encoding/json"
	"time"
)

type SanitizerEnum string

const (
	SANITIZER_ASAN    SanitizerEnum = "ASAN"
	SANITIZER_UBSAN   SanitizerEnum = "UBSAN"
	SANITIZER_MSAN    SanitizerEnum = "MSAN"
	SANITIZER_JAZZER  SanitizerEnum = "JAZZER"
	SANITIZER_UNKNOWN SanitizerEnum = "UNKNOWN"
)

type Bug struct {
	ID           uint            `gorm:"primaryKey;autoIncrement"`
	TaskID       string          `gorm:"column:task_id;not null"`
	CreatedAt    time.Time       `gorm:"default:current_timestamp"`
	Architecture string          `gorm:"not null"`
	POC          string          `gorm:"column:poc;not null"`
	HarnessName  string          `gorm:"column:harness_name;not null"`
	Sanitizer    SanitizerEnum   `gorm:"type:sanitizerenum;not null"`
	SARIFReport  json.RawMessage `gorm:"column:sarif_report;type:jsonb"`

	Task Task `gorm:"foreignKey:TaskID;references:ID"`
}

type BugProfile struct {
	ID               uint   `gorm:"primaryKey;autoIncrement"`
	SanitizerBugType string `gorm:"column:sanitizer_bug_type;not null"`
	TriggerPoint     string `gorm:"column:trigger_point;not null"`
	Summary          string `gorm:"column:summary;not null"`
}

type BugGroup struct {
	ID           uint      `gorm:"primaryKey;autoIncrement"`
	BugID        uint      `gorm:"column:bug_id;not null"`
	BugProfileID uint      `gorm:"column:bug_profile_id;not null"`
	CreatedAt    time.Time `gorm:"default:current_timestamp"`

	Bug        Bug        `gorm:"foreignKey:BugID;references:ID"`
	BugProfile BugProfile `gorm:"foreignKey:BugProfileID;references:ID"`
}

package models

import (
	"encoding/json"
	"time"
)

// User model
type User struct {
	ID        uint      `gorm:"primaryKey;autoIncrement"`
	Username  string    `gorm:"unique;not null"`
	Password  string    `gorm:"not null"`
	CreatedAt time.Time `gorm:"default:current_timestamp"`
}

// Message model
type Message struct {
	ID          string    `gorm:"primaryKey;not null"`
	MessageTime int64     `gorm:"not null"`
	CreatedAt   time.Time `gorm:"default:current_timestamp"`
}

// Task model
type Task struct {
	ID          string          `gorm:"primaryKey;not null"`
	UserID      uint            `gorm:"not null"`
	MessageID   string          `gorm:"not null"`
	Deadline    int64           `gorm:"not null"`
	Focus       string          `gorm:"not null"`
	ProjectName string          `gorm:"not null"`
	TaskType    string          `gorm:"type:tasktypeenum;not null"`
	Status      string          `gorm:"type:taskstatusenum;not null"`
	CreatedAt   time.Time       `gorm:"default:current_timestamp"`
	Metadata    json.RawMessage `gorm:"type:json"`

	User    User    `gorm:"foreignKey:UserID;references:ID"`
	Message Message `gorm:"foreignKey:MessageID;references:ID"`
}

// Source model
type Source struct {
	ID         uint   `gorm:"primaryKey;autoIncrement"`
	TaskID     string `gorm:"not null"`
	SHA256     string `gorm:"not null;size:64"`
	SourceType string `gorm:"type:sourcetypeenum;not null"`
	URL        string `gorm:"not null"`
	Path       string `gorm:"default:null"`

	Task Task `gorm:"foreignKey:TaskID;references:ID"`
}

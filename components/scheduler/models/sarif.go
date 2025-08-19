package models

import "time"

// Sarif model
type Sarif struct {
	ID        string    `gorm:"primaryKey;not null"`
	TaskID    string    `gorm:"not null"`
	MessageID string    `gorm:"not null"`
	Sarif     string    `gorm:"type:jsonb;not null"`
	CreatedAt time.Time `gorm:"default:current_timestamp"`

	Task    Task    `gorm:"foreignKey:TaskID;references:ID"`
	Message Message `gorm:"foreignKey:MessageID;references:ID"`
}

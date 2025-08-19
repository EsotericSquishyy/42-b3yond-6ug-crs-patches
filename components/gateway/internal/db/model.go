package db

import (
	"time"

	"gorm.io/datatypes"
)

// ---------------------------------------------------------------------
// Enum types
// ---------------------------------------------------------------------

type TaskTypeEnum string

const (
	TaskTypeFull  TaskTypeEnum = "full"
	TaskTypeDelta TaskTypeEnum = "delta"
)

type TaskStatusEnum string

const (
	TaskStatusCanceled   TaskStatusEnum = "canceled"
	TaskStatusErrored    TaskStatusEnum = "errored"
	TaskStatusPending    TaskStatusEnum = "pending"
	TaskStatusProcessing TaskStatusEnum = "processing"
	TaskStatusSucceeded  TaskStatusEnum = "succeeded"
	TaskStatusFailed     TaskStatusEnum = "failed"
	TaskStatusWaiting    TaskStatusEnum = "waiting"
)

type SourceTypeEnum string

const (
	SourceTypeRepo        SourceTypeEnum = "repo"
	SourceTypeFuzzTooling SourceTypeEnum = "fuzz_tooling"
	SourceTypeDiff        SourceTypeEnum = "diff"
)

type FuzzerTypeEnum string

const (
	FuzzerTypeSeedgen  FuzzerTypeEnum = "seedgen"
	FuzzerTypePrime    FuzzerTypeEnum = "prime"
	FuzzerTypeGeneral  FuzzerTypeEnum = "general"
	FuzzerTypeDirected FuzzerTypeEnum = "directed"
)

type SanitizerEnum string

const (
	SanitizerASAN    SanitizerEnum = "ASAN"
	SanitizerUBSAN   SanitizerEnum = "UBSAN"
	SanitizerMSAN    SanitizerEnum = "MSAN"
	SanitizerJAZZER  SanitizerEnum = "JAZZER"
	SanitizerUNKNOWN SanitizerEnum = "UNKNOWN"
)

// ---------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------

// User represents the users table.
type User struct {
	ID        int       `gorm:"primaryKey;column:id" json:"id"`
	Username  string    `gorm:"column:username;not null;unique" json:"username"`
	Password  string    `gorm:"column:password;not null" json:"password"`
	CreatedAt time.Time `gorm:"column:created_at;default:now()" json:"created_at"`
}

func (User) TableName() string {
	return "users"
}

// Message represents the messages table.
type Message struct {
   ID          string    `gorm:"primaryKey;column:id" json:"id"`
   MessageTime int64     `gorm:"column:message_time;not null" json:"message_time"`
   HTTPMethod  string    `gorm:"column:http_method" json:"http_method"`
   RawEndpoint string    `gorm:"column:raw_endpoint" json:"raw_endpoint"`
   HTTPBody    string    `gorm:"column:http_body;type:text" json:"http_body"`
   CreatedAt   time.Time `gorm:"column:created_at;default:now()" json:"created_at"`
}

func (Message) TableName() string {
	return "messages"
}

// Task represents the tasks table.
type Task struct {
	ID          string         `gorm:"primaryKey;column:id" json:"id"`
	UserID      int            `gorm:"column:user_id;not null" json:"user_id"`
	MessageID   string         `gorm:"column:message_id;not null" json:"message_id"`
	Deadline    int64          `gorm:"column:deadline;not null" json:"deadline"`
	Focus       string         `gorm:"column:focus;not null" json:"focus"`
	ProjectName string         `gorm:"column:project_name;not null" json:"project_name"`
	TaskType    TaskTypeEnum   `gorm:"column:task_type;not null" json:"task_type"`
	Status      TaskStatusEnum `gorm:"column:status;not null" json:"status"`
	CreatedAt   time.Time      `gorm:"column:created_at;default:now()" json:"created_at"`
	Metadata    datatypes.JSON `gorm:"column:metadata;type:jsonb" json:"metadata"`
}

func (Task) TableName() string {
	return "tasks"
}

// Source represents the sources table.
type Source struct {
	ID         int            `gorm:"primaryKey;column:id" json:"id"`
	TaskID     string         `gorm:"column:task_id;not null" json:"task_id"`
	SHA256     string         `gorm:"column:sha256;size:64;not null" json:"sha256"`
	SourceType SourceTypeEnum `gorm:"column:source_type;not null" json:"source_type"`
	URL        string         `gorm:"column:url;not null" json:"url"`
	Path       *string        `gorm:"column:path" json:"path,omitempty"`
}

func (Source) TableName() string {
	return "sources"
}

// Sarif represents the sarifs table.
type Sarif struct {
	ID        string         `gorm:"primaryKey;column:id" json:"id"`
	TaskID    string         `gorm:"column:task_id;not null" json:"task_id"`
	MessageID string         `gorm:"column:message_id;not null" json:"message_id"`
	Sarif     datatypes.JSON `gorm:"column:sarif;type:jsonb;not null" json:"sarif"`
	CreatedAt time.Time      `gorm:"column:created_at;default:now()" json:"created_at"`
	Metadata  datatypes.JSON `gorm:"column:metadata;type:jsonb" json:"metadata"`
}

func (Sarif) TableName() string {
	return "sarifs"
}

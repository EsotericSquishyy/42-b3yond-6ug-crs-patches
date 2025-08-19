package services

import (
	"crs-gateway/gen/models"
	"crs-gateway/internal/db"
	"encoding/json"
	"errors"
	"fmt"

	"gorm.io/datatypes"
	"gorm.io/gorm"
)

// Common errors
var (
	ErrInvalidTaskType   = errors.New("invalid task type")
	ErrInvalidSourceType = errors.New("invalid source type")
	ErrMarshalMetadata   = errors.New("failed to marshal metadata")
)

// TaskService defines the interface for task-related operations
type TaskService interface {
	CreateTask(task *models.TypesTask, messageID string, userID int) error
	CancelTask(taskID string) error
	CancelAllTasks() error
}

// TaskServiceImpl implements TaskService interface
type TaskServiceImpl struct {
	db *gorm.DB
}

// NewTaskService creates a new instance of TaskService
func NewTaskService(db *gorm.DB) TaskService {
	return &TaskServiceImpl{
		db: db,
	}
}

// CreateTask creates a new task and associated records in the database
func (s *TaskServiceImpl) CreateTask(task *models.TypesTask, messageID string, userID int) error {
	for _, t := range task.Tasks {
		if err := s.createSingleTask(t, messageID, userID); err != nil {
			return fmt.Errorf("failed to create task: %w", err)
		}
	}

	return nil
}

func (s *TaskServiceImpl) CancelTask(taskID string) error {
	task := &db.Task{
		ID: taskID,
	}

	if err := s.db.Model(task).Update("status", db.TaskStatusCanceled).Error; err != nil {
		return fmt.Errorf("failed to cancel task: %w", err)
	}

	return nil
}

func (s *TaskServiceImpl) CancelAllTasks() error {
	// Only cancel tasks that are not already in a final state
	if err := s.db.Model(&db.Task{}).
		Where("status NOT IN (?)", []db.TaskStatusEnum{db.TaskStatusCanceled, db.TaskStatusSucceeded, db.TaskStatusFailed}).
		Update("status", db.TaskStatusCanceled).Error; err != nil {
		return fmt.Errorf("failed to cancel all tasks: %w", err)
	}

	return nil
}

// createSingleTask handles the creation of a single task and its sources
func (s *TaskServiceImpl) createSingleTask(t *models.TypesTaskDetail, messageID string, userID int) error {
	// ignore tasks with no harnesses
	if !*t.HarnessesIncluded {
		return nil
	}

	dbTaskType, err := getTaskType(*t.Type)
	if err != nil {
		return err
	}

	metadataJSON, err := json.Marshal(t.Metadata)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrMarshalMetadata, err)
	}

	task := &db.Task{
		ID:          t.TaskID.String(),
		UserID:      userID,
		MessageID:   messageID,
		Deadline:    *t.Deadline,
		Focus:       *t.Focus,
		ProjectName: *t.ProjectName,
		TaskType:    dbTaskType,
		Status:      db.TaskStatusPending,
		Metadata:    datatypes.JSON(metadataJSON),
	}

	if err := s.db.Create(task).Error; err != nil {
		return fmt.Errorf("failed to create task record: %w", err)
	}

	if err := s.createSources(t.Source, task.ID); err != nil {
		return fmt.Errorf("failed to create sources: %w", err)
	}

	return nil
}

// createSources creates source records for a task
func (s *TaskServiceImpl) createSources(sources []*models.TypesSourceDetail, taskID string) error {
	for _, src := range sources {
		dbSourceType, err := getSourceType(*src.Type)
		if err != nil {
			return err
		}

		source := &db.Source{
			TaskID:     taskID,
			SHA256:     *src.Sha256,
			SourceType: dbSourceType,
			URL:        *src.URL,
		}

		if err := s.db.Create(source).Error; err != nil {
			return fmt.Errorf("failed to create source: %w", err)
		}
	}
	return nil
}

// getTaskType converts API task type to database task type
func getTaskType(apiTaskType models.TypesTaskType) (db.TaskTypeEnum, error) {
	switch apiTaskType {
	case models.TypesTaskTypeFull:
		return db.TaskTypeFull, nil
	case models.TypesTaskTypeDelta:
		return db.TaskTypeDelta, nil
	default:
		return "", fmt.Errorf("%w: %s", ErrInvalidTaskType, apiTaskType)
	}
}

// getSourceType converts API source type to database source type
func getSourceType(apiSourceType models.TypesSourceType) (db.SourceTypeEnum, error) {
	switch apiSourceType {
	case models.TypesSourceTypeRepo:
		return db.SourceTypeRepo, nil
	case models.TypesSourceTypeFuzzDashTooling:
		return db.SourceTypeFuzzTooling, nil
	case models.TypesSourceTypeDiff:
		return db.SourceTypeDiff, nil
	default:
		return "", fmt.Errorf("%w: %s", ErrInvalidSourceType, apiSourceType)
	}
}

package repository

import (
	"crs-scheduler/models"

	"gorm.io/gorm"
)

type TaskRepository interface {
	GetTaskByID(taskID string) (models.Task, error)
	GetPendingTasks() ([]models.Task, error)
	GetProcessingTasks() ([]models.Task, error)
	UpdateTaskStatus(taskID string, status string) error
	GetSources(taskID string) ([]models.Source, error)
	UpdateSourcePath(sourceID uint, path string) error
}

type TaskRepositoryImpl struct {
	db *gorm.DB
}

func NewTaskRepository(db *gorm.DB) TaskRepository {
	return &TaskRepositoryImpl{db: db}
}

func (r *TaskRepositoryImpl) GetPendingTasks() ([]models.Task, error) {
	var tasks []models.Task
	result := r.db.Where("status = ?", "pending").Find(&tasks)
	if result.Error != nil {
		return nil, result.Error
	}
	return tasks, nil
}

func (r *TaskRepositoryImpl) GetProcessingTasks() ([]models.Task, error) {
	var tasks []models.Task
	result := r.db.Where("status IN ?", []string{"processing", "waiting"}).Find(&tasks)
	if result.Error != nil {
		return nil, result.Error
	}
	return tasks, nil
}

func (r *TaskRepositoryImpl) UpdateTaskStatus(taskID string, status string) error {
	result := r.db.Model(&models.Task{}).Where("id = ?", taskID).Update("status", status)
	return result.Error
}

func (r *TaskRepositoryImpl) GetTaskByID(taskID string) (models.Task, error) {
	var task models.Task
	result := r.db.Where("id = ?", taskID).First(&task)
	if result.Error != nil {
		return models.Task{}, result.Error
	}
	return task, nil
}

func (r *TaskRepositoryImpl) GetSources(taskID string) ([]models.Source, error) {
	var sources []models.Source
	result := r.db.Where("task_id = ?", taskID).Find(&sources)
	if result.Error != nil {
		return nil, result.Error
	}
	return sources, nil
}

func (r *TaskRepositoryImpl) UpdateSourcePath(sourceID uint, path string) error {
	result := r.db.Model(&models.Source{}).Where("id = ?", sourceID).Update("path", path)
	return result.Error
}

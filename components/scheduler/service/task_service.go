package service

import (
	"context"
	"crs-scheduler/internal/messaging"
	"crs-scheduler/models"
	"crs-scheduler/repository"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"

	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

const (
	TaskFailureCountKey = "scheduler:task_failure_count"
	BroadcastedTasksKey = "scheduler:broadcasted_tasks"
)

type TaskService interface {
	// New tasks
	GetPendingTasks() ([]models.Task, error)
	// modify the status of the task
	MarkTaskAsProcessing(taskID string) error
	MarkTaskAsError(taskID string) error
	MarkTaskAsSucceeded(taskID string) error
	// download the sources and set `path` for the sources
	DownloadSources(taskID string) error
	// get the task queue element
	GetTaskQueueElement(taskID string) (map[string]any, error)
	// failure count
	IncrementFailureCount(taskID string) (int, error)
	GetFailureCount(taskID string) (int, error)
	ResetFailureCount(taskID string) error
	// Broadcasted task management
	SaveBroadcastedTask(taskID string) error
	GetBroadcastedTasks() ([]string, error)
	RemoveBroadcastedTask(taskID string) error
	GetTask(taskID string) (models.Task, error)
	// set task metadata
	SetTaskMetadata(taskID string, metadata json.RawMessage) error
}

type TaskServiceParams struct {
	fx.In

	TaskRepo    repository.TaskRepository
	RabbitMQ    messaging.RabbitMQ
	Logger      *zap.Logger
	RedisClient *redis.Client
}

type TaskServiceImpl struct {
	taskRepo    repository.TaskRepository
	rabbitMQ    messaging.RabbitMQ
	logger      *zap.Logger
	redisClient *redis.Client
}

func NewTaskService(params TaskServiceParams) TaskService {
	return &TaskServiceImpl{
		taskRepo:    params.TaskRepo,
		rabbitMQ:    params.RabbitMQ,
		logger:      params.Logger,
		redisClient: params.RedisClient,
	}
}

func (s *TaskServiceImpl) GetPendingTasks() ([]models.Task, error) {
	return s.taskRepo.GetPendingTasks()
}

func (s *TaskServiceImpl) MarkTaskAsProcessing(taskID string) error {
	return s.taskRepo.UpdateTaskStatus(taskID, "processing")
}

func (s *TaskServiceImpl) MarkTaskAsError(taskID string) error {
	return s.taskRepo.UpdateTaskStatus(taskID, "errored")
}

func (s *TaskServiceImpl) MarkTaskAsSucceeded(taskID string) error {
	return s.taskRepo.UpdateTaskStatus(taskID, "succeeded")
}

func (s *TaskServiceImpl) DownloadSources(taskID string) error {
	task, err := s.taskRepo.GetTaskByID(taskID)
	if err != nil {
		return err
	}

	sources, err := s.taskRepo.GetSources(taskID)
	if err != nil {
		return err
	}

	valid := s.checkSourceValidity(task, sources)

	if !valid {
		return fmt.Errorf("invalid sources for task: %s", taskID)
	}

	// download the sources and set `path` for the sources
	_, err = s.preprocessSources(sources, taskID)
	if err != nil {
		return err
	}

	return nil
}

func (s *TaskServiceImpl) GetTaskQueueElement(taskID string) (map[string]any, error) {
	task, err := s.taskRepo.GetTaskByID(taskID)
	if err != nil {
		return nil, err
	}

	sources, err := s.taskRepo.GetSources(taskID)
	if err != nil {
		return nil, err
	}

	sourcePaths := make(map[string]string)
	repoPaths := make([]string, 0)
	for _, source := range sources {
		if source.SourceType == "repo" {
			repoPaths = append(repoPaths, source.Path)
		} else {
			sourcePaths[source.SourceType] = source.Path
		}
	}

	// Build base task data
	taskData := map[string]any{
		"task_id":         task.ID,
		"task_type":       task.TaskType,
		"project_name":    task.ProjectName,
		"focus":           task.Focus,
		"repo":            repoPaths,
		"fuzzing_tooling": sourcePaths["fuzz_tooling"],
	}

	// Add diff URL for delta tasks
	if task.TaskType == "delta" {
		taskData["diff"] = sourcePaths["diff"]
	}

	return taskData, nil
}

// For a task, check if the sources are valid and complete to proceed
func (s *TaskServiceImpl) checkSourceValidity(task models.Task, sources []models.Source) bool {
	sourceTypeRequirements := map[string][]string{
		"full":  {"repo", "fuzz_tooling"},
		"delta": {"repo", "fuzz_tooling", "diff"},
	}

	requiredTypes, ok := sourceTypeRequirements[task.TaskType]
	if !ok {
		s.logger.Error("unknown task type", zap.String("task_type", task.TaskType))
		return false
	}

	foundTypes := make(map[string]bool)
	for _, source := range sources {
		foundTypes[source.SourceType] = true
	}

	for _, requiredType := range requiredTypes {
		if !foundTypes[requiredType] {
			s.logger.Error("missing required source type", zap.String("task_type", task.TaskType), zap.String("source_type", requiredType))
			return false
		}
	}

	return true
}

// Get the sources for a task, download them, verify their SHA256, and return the sources with the local file path
func (s *TaskServiceImpl) preprocessSources(sources []models.Source, taskID string) ([]models.Source, error) {
	crsDir := "/crs"
	if _, err := os.Stat(crsDir); os.IsNotExist(err) {
		return nil, fmt.Errorf("CRS directory does not exist: %s", crsDir)
	}

	// Create task directory (crs/<task_id>)
	taskDir := filepath.Join(crsDir, taskID)
	if err := os.MkdirAll(taskDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create task directory: %w", err)
	}

	// Download and verify each source
	for i, source := range sources {
		path, err := downloadAndVerifyFile(source.URL, source.SHA256, taskDir)
		if err != nil {
			return nil, err
		}
		// Update source with local file path
		sources[i].Path = path
	}

	// update the sources in the database
	for _, source := range sources {
		err := s.taskRepo.UpdateSourcePath(source.ID, source.Path)
		if err != nil {
			return nil, err
		}
	}

	return sources, nil
}

func downloadAndVerifyFile(sourceUrl string, sha256Hash string, folder string) (string, error) {
	parsedURL, err := url.Parse(sourceUrl)
	if err != nil {
		return "", fmt.Errorf("failed to parse URL %s: %w", sourceUrl, err)
	}
	urlPath := parsedURL.Path                      // path without query params or fragment
	urlFilename := filepath.Base(urlPath)          // get the last part of the path
	filename := filepath.Join(folder, urlFilename) // prepend the folder path to the filename

	// If file already exists, delete the old file
	if _, err := os.Stat(filename); !os.IsNotExist(err) {
		os.Remove(filename)
	}

	// Download file
	resp, err := http.Get(sourceUrl)
	if err != nil {
		return "", fmt.Errorf("failed to download file %s: %w", sourceUrl, err)
	}
	defer resp.Body.Close()

	// Create destination file
	out, err := os.Create(filename)
	if err != nil {
		return "", fmt.Errorf("failed to create file %s: %w", filename, err)
	}
	defer out.Close()

	// Calculate SHA256 while copying
	hash := sha256.New()
	writer := io.MultiWriter(out, hash)

	if _, err := io.Copy(writer, resp.Body); err != nil {
		return "", fmt.Errorf("failed to save file %s: %w", filename, err)
	}

	// Verify SHA256
	calculatedHash := hex.EncodeToString(hash.Sum(nil))
	if calculatedHash != sha256Hash {
		return "", fmt.Errorf("SHA256 mismatch for %s: expected %s, got %s",
			sourceUrl, sha256Hash, calculatedHash)
	}

	return filename, nil
}

func (s *TaskServiceImpl) IncrementFailureCount(taskID string) (int, error) {
	key := TaskFailureCountKey + ":" + taskID
	count, err := s.redisClient.Incr(context.Background(), key).Result()
	if err != nil {
		return 0, err
	}
	return int(count), nil
}

func (s *TaskServiceImpl) GetFailureCount(taskID string) (int, error) {
	key := TaskFailureCountKey + ":" + taskID
	count, err := s.redisClient.Get(context.Background(), key).Int()
	if err == redis.Nil {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	return count, nil
}

func (s *TaskServiceImpl) ResetFailureCount(taskID string) error {
	key := TaskFailureCountKey + ":" + taskID
	return s.redisClient.Del(context.Background(), key).Err()
}

// SaveBroadcastedTask saves a task ID to the broadcasted tasks set in Redis
func (s *TaskServiceImpl) SaveBroadcastedTask(taskID string) error {
	key := BroadcastedTasksKey
	return s.redisClient.SAdd(context.Background(), key, taskID).Err()
}

// GetBroadcastedTasks returns all task IDs from the broadcasted tasks set
func (s *TaskServiceImpl) GetBroadcastedTasks() ([]string, error) {
	key := BroadcastedTasksKey
	return s.redisClient.SMembers(context.Background(), key).Result()
}

// RemoveBroadcastedTask removes a task ID from the broadcasted tasks set
func (s *TaskServiceImpl) RemoveBroadcastedTask(taskID string) error {
	key := BroadcastedTasksKey
	return s.redisClient.SRem(context.Background(), key, taskID).Err()
}

// GetTask returns a task by its ID
func (s *TaskServiceImpl) GetTask(taskID string) (models.Task, error) {
	return s.taskRepo.GetTaskByID(taskID)
}

func (s *TaskServiceImpl) SetTaskMetadata(taskID string, metadata json.RawMessage) error {
	key := "global:task_metadata:" + taskID
	return s.redisClient.Set(context.Background(), key, string(metadata), 0).Err()
}

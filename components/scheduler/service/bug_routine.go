package service

import (
	"bytes"
	"context"
	"crs-scheduler/internal/messaging"
	"crs-scheduler/internal/scheduler"
	"crs-scheduler/repository"
	"encoding/json"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

const (
	MaxBugIDKey = "scheduler:max_bug_id"
)

type BugRoutine struct {
	bugRepo     repository.BugRepository
	taskService TaskService
	rabbitMQ    messaging.RabbitMQ
	redisClient *redis.Client
	logger      *zap.Logger
}

type BugRoutineParams struct {
	fx.In

	BugRepo     repository.BugRepository
	TaskService TaskService
	RabbitMQ    messaging.RabbitMQ
	RedisClient *redis.Client
	Logger      *zap.Logger
}

func NewBugRoutine(params BugRoutineParams) scheduler.ScheduleRoutine {
	// Initialize maxBugID in Redis if it doesn't exist
	maxBugID, err := params.BugRepo.GetMaxBugID()
	if err != nil {
		params.Logger.Error("failed to get max bug id", zap.Error(err))
		return nil
	}

	err = params.RedisClient.SetNX(
		context.Background(),
		MaxBugIDKey,
		maxBugID,
		0, // 0 means no expiration
	).Err()
	if err != nil {
		params.Logger.Error("failed to initialize max bug id in redis", zap.Error(err))
		return nil
	}

	return &BugRoutine{
		bugRepo:     params.BugRepo,
		taskService: params.TaskService,
		rabbitMQ:    params.RabbitMQ,
		redisClient: params.RedisClient,
		logger:      params.Logger,
	}
}

func (r *BugRoutine) Run() error {
	// Get current maxBugID from Redis
	maxBugID, err := r.redisClient.Get(context.Background(), MaxBugIDKey).Int64()
	if err != nil {
		r.logger.Error("failed to get max bug id from redis", zap.Error(err))
		return err
	}

	r.logger.Debug("getting new bug ids", zap.Int64("maxBugID", maxBugID))

	bugs, err := r.bugRepo.GetNewBugs(maxBugID)
	if err != nil {
		r.logger.Error("failed to get new bugs", zap.Error(err))
		return err
	}

	for _, bug := range bugs {
		// get task details
		task_queue_element, err := r.taskService.GetTaskQueueElement(bug.TaskID)
		if err != nil {
			r.logger.Error("Failed to get task queue element",
				zap.String("task_id", bug.TaskID),
				zap.Error(err))
			continue
		}

		// append bug to task_queue_element
		task_queue_element["bug_id"] = bug.ID
		task_queue_element["poc_path"] = bug.POC
		task_queue_element["harness_name"] = bug.HarnessName
		task_queue_element["sanitizer"] = bug.Sanitizer

		// figure out the priority
		var priority uint8
		switch bug.Sanitizer {
		case "address":
			priority = 4
		case "memory":
			priority = 2
		case "undefined":
			priority = 1
		default:
			priority = 3
		}

		// Encode the task queue element
		var buffer bytes.Buffer
		encoder := json.NewEncoder(&buffer)
		encoder.SetEscapeHTML(false)
		if err := encoder.Encode(task_queue_element); err != nil {
			r.logger.Error("Failed to encode task queue element",
				zap.String("task_id", bug.TaskID),
				zap.Error(err))
			continue
		}

		// Publish to the triage queue
		ch := r.rabbitMQ.GetChannel()
		defer ch.Close()

		err = ch.Publish(
			messaging.DirectExchange, // exchange
			messaging.TriageQueue,    // routing key
			false,                    // mandatory
			false,                    // immediate
			amqp.Publishing{
				ContentType: "application/json",
				Body:        buffer.Bytes(),
				Priority:    priority,
			},
		)
		if err != nil {
			r.logger.Error("Failed to publish to triage queue",
				zap.String("task_id", bug.TaskID),
				zap.Uint("bug_id", bug.ID),
				zap.Error(err))
			continue
		}

		// Mark the bug as forwarded by updating the "max_bug_id" in redis
		err = r.redisClient.Set(
			context.Background(),
			MaxBugIDKey,
			bug.ID,
			0, // 0 means no expiration
		).Err()
		if err != nil {
			r.logger.Error("Failed to update max bug id in redis", zap.Error(err))
			continue
		}
	}

	return nil
}

func (r *BugRoutine) Cancel() {
}

func (r *BugRoutine) Name() string {
	return "BugRoutine"
}

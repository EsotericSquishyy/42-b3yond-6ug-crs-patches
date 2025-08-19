package builder

import (
	"b3fuzz/config"
	"b3fuzz/internal/seeds"
	"b3fuzz/internal/utils"
	"b3fuzz/pkg/mq"
	"b3fuzz/pkg/telemetry"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/google/uuid"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

const (
	ArtifactQueueName = "artifact_queue"
	LibCminPath       = "/libcmin.a"
	MetadataKey       = "global:task_metadata:%s"
	TaskTraceCtxKey   = "global:trace_context:%s"
	BuildTraceCtxKey  = "artifacts:trace_context:%s"
)

// received from RabbitMQ
type TaskConfig struct {
	TaskId         string   `json:"task_id"`
	TaskType       string   `json:"task_type"`
	ProjectName    string   `json:"project_name"`
	Focus          string   `json:"focus"`
	Repo           []string `json:"repo"`            // Repository paths
	FuzzingTooling string   `json:"fuzzing_tooling"` // Path to fuzzing tools
	Diff           string   `json:"diff,omitempty"`  // Optional diff URL for delta tasks
}

type TaskMetadata map[string]any // Metadata for the task, stored in Redis

// Internal state for the builder
type TaskDetails struct {
	TaskID          string
	ProjectName     string // name of the project
	RepoPath        string // path to the focus repo dir; patch should be already applied in this dir
	FuzzToolingPath string // path to the fuzz tooling (oss-fuzz) dir
}

// Clone creates a copy of the TaskDetails with a new temporary directory for the repo and fuzz tooling.
// If the copy fails, fall back to the original directory.
func (d *TaskDetails) clone() *TaskDetails {
	tempDirUUID := uuid.New().String()
	tempDir := filepath.Join(os.TempDir(), "b3fuzz-temp-"+tempDirUUID)
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		return d
	}
	// Copy the repo and fuzz tooling directories to the temp dir
	newRepoPath := filepath.Join(tempDir, filepath.Base(d.RepoPath))
	if err := utils.CopyDir(d.RepoPath, filepath.Join(tempDir, filepath.Base(d.RepoPath))); err != nil {
		return d
	}
	newFuzzToolingPath := filepath.Join(tempDir, filepath.Base(d.FuzzToolingPath))
	if err := utils.CopyDir(d.FuzzToolingPath, newFuzzToolingPath); err != nil {
		return d
	}
	return &TaskDetails{
		TaskID:          d.TaskID,
		ProjectName:     d.ProjectName,
		RepoPath:        newRepoPath,
		FuzzToolingPath: newFuzzToolingPath,
	}
}

type TaskBuilder struct {
	logger        *zap.Logger
	rabbitMQ      mq.RabbitMQ // builder receive messages from message queue
	redisClient   *redis.Client
	seedManager   *seeds.SeedManager
	tracerFactory *telemetry.TracerFactory
	coreCount     int
	shutdowner    fx.Shutdowner

	// state
	taskDetails map[string]*TaskDetails // task_id -> task details
	failedCount map[string]int          // task_id -> failed count

	// settings
	localDir string
}

type TaskBuilderParams struct {
	fx.In

	Logger        *zap.Logger
	RabbitMQ      mq.RabbitMQ
	RedisClient   *redis.Client
	SeedManager   *seeds.SeedManager
	Config        *config.AppConfig
	TracerFactory *telemetry.TracerFactory
	Shutdowner    fx.Shutdowner
}

func StartTaskBuilder(p TaskBuilderParams, ctx context.Context /* app context */) *TaskBuilder {
	// create local dir if not exists
	localDir := filepath.Join(os.TempDir(), "b3fuzz")
	if err := os.MkdirAll(localDir, 0755); err != nil {
		p.Logger.Fatal("Failed to create local dir", zap.Error(err))
	}

	builder := &TaskBuilder{
		p.Logger,
		p.RabbitMQ,
		p.RedisClient,
		p.SeedManager,
		p.TracerFactory,
		p.Config.CoreCount,
		p.Shutdowner,
		make(map[string]*TaskDetails),
		make(map[string]int),
		localDir,
	}

	go builder.start(ctx)
	return builder
}

func (b *TaskBuilder) start(ctx context.Context) {
	const retryLimit = 3
	failCnt := 0

	for {
		errChan := make(chan error)

		// start listening in a separate goroutine
		go func() {
			errChan <- b.listen(ctx)
		}()

		select {
		case <-ctx.Done():
			// context canceled, exit the loop
			return
		case err := <-errChan:
			if err != nil {
				b.logger.Warn("Task builder failed to listen for messages", zap.Error(err))
				failCnt++

				if failCnt >= retryLimit {
					b.logger.Warn("Retry limit reached, shutting down...", zap.Error(err))
					b.shutdowner.Shutdown()
					return
				}
			}
			b.logger.Warn("retrying...")
		}
	}
}

// Listen initializes the task builder and starts listening for messages
func (b *TaskBuilder) listen(ctx context.Context) error {
	b.logger.Info("Starting task listener")

	channel := b.rabbitMQ.GetChannel()
	defer channel.Close()
	if channel == nil {
		b.logger.Error("failed to get RabbitMQ channel")
		return fmt.Errorf("failed to get RabbitMQ channel")
	}

	// Set QoS to limit the number of unacknowledged messages
	if err := channel.Qos(1, 0, false); err != nil {
		b.logger.Error("failed to set QoS", zap.Error(err))
		return fmt.Errorf("failed to set QoS: %w", err)
	}

	// decalre the queue (idempotent)
	// this is a no-op if the queue already exists
	q, err := channel.QueueDeclare(
		ArtifactQueueName,
		true,  // durable
		false, // delete when unused
		false, // exclusive
		false, // no-wait
		nil,   // arguments
	)
	if err != nil {
		b.logger.Error("failed to declare queue", zap.Error(err))
		return fmt.Errorf("failed to declare queue: %w", err)
	}

	// Create message consume channel
	b.logger.Info("Waiting for messages in queue", zap.String("queue", q.Name))
	msg, err := channel.Consume(
		q.Name,
		"",    // consumer
		false, // auto-ack
		false, // exclusive
		false, // no-local
		false, // no-wait
		nil,   // args
	)
	if err != nil {
		b.logger.Error("failed to register consumer", zap.Error(err))
		return fmt.Errorf("failed to register consumer: %w", err)
	}

	errChan := make(chan error)

	go func() {
		for {
			select {
			case <-ctx.Done():
				b.logger.Info("Context done, stopping message consumer")
				return
			case message, ok := <-msg:
				if !ok {
					b.logger.Error("Channel closed, stopping message consumer")
					errChan <- fmt.Errorf("channel closed")
					return
				}
				if err := b.onMessage(ctx, message); err != nil {
					b.logger.Error("Failed to handle message", zap.Error(err))
					errChan <- err
				}
			}
		}
	}()

	select {
	case <-ctx.Done():
		return nil
	case err := <-errChan:
		return err
	}
}

func (b *TaskBuilder) onMessage(ctx context.Context, message amqp.Delivery) error {
	b.logger.Info("Received message", zap.String("message", string(message.Body)))

	// parse the message
	var taskConfig TaskConfig
	if err := json.Unmarshal(message.Body, &taskConfig); err != nil {
		return fmt.Errorf("failed to unmarshal message: %w", err)
	}

	// grab the task metadata from Redis
	taskMetadata := make(TaskMetadata)
	metadataJsonStr, err := b.redisClient.Get(ctx, fmt.Sprintf(MetadataKey, taskConfig.TaskId)).Result()
	if err != nil {
		b.logger.Error("Failed to get task metadata from Redis", zap.Error(err))
	} else {
		if err := json.Unmarshal([]byte(metadataJsonStr), &taskMetadata); err != nil {
			b.logger.Error("Failed to unmarshal task metadata", zap.Error(err))
		} else {
			b.logger.Info("Task metadata retrieved from Redis", zap.Any("metadata", taskMetadata))
		}
	}

	// if a task cannot finish building in 4 hours, we will stop it
	buildCtx, cancel := context.WithTimeout(ctx, 4*time.Hour) // 4 hours timeout for the task
	defer cancel()

	// create a new tracer for this task
	tracerJsonStr, err := b.redisClient.Get(buildCtx, fmt.Sprintf(TaskTraceCtxKey, taskConfig.TaskId)).Result()
	if err != nil {
		b.logger.Error("Failed to get trace context from Redis", zap.Error(err))
	}
	tracer := b.tracerFactory.NewTracerSpawnedFrom(buildCtx, tracerJsonStr, "building artifacts").
		WithAttributes(
			telemetry.NewSpanAttributes(telemetry.Building).
				WithExtraAttributes(taskMetadata),
		)
	tracer.Start()
	defer tracer.End()

	// and inject it into the context
	buildCtx = context.WithValue(buildCtx, telemetry.TracerKey{}, tracer)
	if err := b.redisClient.Set(buildCtx, fmt.Sprintf(BuildTraceCtxKey, taskConfig.TaskId), tracer.Export(), 0).Err(); err != nil {
		b.logger.Error("Failed to set trace context in Redis", zap.Error(err))
	}

	if err := b.buildTask(buildCtx, taskConfig); err != nil {
		b.logger.Error("Failed to build task", zap.Error(err))
		b.logger.Error("Failed to build task", zap.Error(err))

		// increase the failed count. If retried 3 times, we will not retry again
		b.failedCount[taskConfig.TaskId] += 1
		isRequeue := b.failedCount[taskConfig.TaskId] < 3
		if err := message.Nack(false, isRequeue); err != nil {
			b.logger.Error("Failed to nack message", zap.Error(err))
			b.shutdowner.Shutdown()
		}

		return fmt.Errorf("failed to build task: %w", err)
	}

	// ACK the message
	if err := message.Ack(false); err != nil {
		b.logger.Error("Failed to ack message", zap.Error(err))
		return fmt.Errorf("failed to ack message: %w", err)
	}

	return nil
}

func (b *TaskBuilder) buildTask(ctx context.Context, taskConfig TaskConfig) error {
	taskDetails, err := b.download(ctx, taskConfig)
	if err != nil {
		b.logger.Error("Failed to download task", zap.Error(err))
		return fmt.Errorf("failed to download task: %w", err)
	}

	lanaguage, _ := b.GetProjectLanguage(ctx, *taskDetails)
	// skip the Java tasks
	if lanaguage == "jvm" {
		b.logger.Info("Skipping Java task", zap.String("taskID", taskConfig.TaskId))
		b.setCminFinishStatus(ctx, taskConfig) // cmin needs to know that task is skipped
		return nil
	}

	if err := b.buildCminArtifacts(ctx, taskConfig, taskDetails.clone()); err != nil {
		b.logger.Error("Failed to build cmin artifacts",
			zap.Error(err),
			zap.String("taskID", taskConfig.TaskId),
			zap.String("projectName", taskConfig.ProjectName))
	}
	b.setCminFinishStatus(ctx, taskConfig)

	if err := b.buildAflArtifacts(ctx, taskConfig, taskDetails); err != nil {
		b.logger.Error("Failed to build afl artifacts",
			zap.Error(err),
			zap.String("taskID", taskConfig.TaskId),
			zap.String("projectName", taskConfig.ProjectName))
		return fmt.Errorf("failed to build afl artifacts: %w", err)
	}

	return nil
}

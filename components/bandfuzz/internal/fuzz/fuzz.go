package fuzz

import (
	"b3fuzz/internal/crash"
	"b3fuzz/internal/seeds"
	"b3fuzz/internal/types"
	"b3fuzz/pkg/telemetry"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"time"

	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

const (
	MetadataKey      = "global:task_metadata:%s"
	TaskTraceCtxKey  = "global:trace_context:%s"
	BuildTraceCtxKey = "artifacts:trace_context:%s"
)

type TaskMetadata map[string]any // Metadata for the task, stored in Redis

type FuzzRunner struct {
	logger        *zap.Logger
	crashManager  *crash.CrashManager
	seedManager   *seeds.SeedManager
	fuzzerMap     map[string]Fuzzer
	tracerFactory *telemetry.TracerFactory
	redisClient   *redis.Client
}

type FuzzRunnerParams struct {
	fx.In
	Logger        *zap.Logger
	CrashManager  *crash.CrashManager
	SeedManager   *seeds.SeedManager
	Fuzzers       []Fuzzer `group:"fuzzers"`
	TracerFactory *telemetry.TracerFactory
	RedisClient   *redis.Client
}

func NewFuzzRunner(params FuzzRunnerParams) *FuzzRunner {
	fuzzMap := make(map[string]Fuzzer)
	for _, fuzzer := range params.Fuzzers {
		fuzzerV := reflect.ValueOf(fuzzer)
		if fuzzerV.Kind() == reflect.Ptr && fuzzerV.IsNil() {
			continue // skip nil fuzzer
		}
		for _, engine := range fuzzer.SupportedEngines() {
			fuzzMap[engine] = fuzzer
			params.Logger.Debug("fuzzer registered", zap.String("engine", engine))
		}
	}

	return &FuzzRunner{
		params.Logger,
		params.CrashManager,
		params.SeedManager,
		fuzzMap,
		params.TracerFactory,
		params.RedisClient,
	}
}

// run the fuzzer with the given timeout. Fuzzing should stop after the timeout is reached.
func (f *FuzzRunner) RunFuzz(ctx context.Context, fuzzlet *types.Fuzzlet, timeout time.Duration) error {
	if fuzzlet == nil {
		f.logger.Error("fuzzlet is nil")
		return errors.New("fuzzlet is nil")
	}

	f.logger.Info("running fuzzlet",
		zap.String("task_id", fuzzlet.TaskId),
		zap.String("harness", fuzzlet.Harness),
		zap.String("sanitizer", fuzzlet.Sanitizer),
		zap.String("engine", fuzzlet.FuzzEngine),
	)

	// grab the task metadata from Redis
	taskMetadata := make(TaskMetadata)
	metadataJsonStr, err := f.redisClient.Get(ctx, fmt.Sprintf(MetadataKey, fuzzlet.TaskId)).Result()
	if err != nil {
		f.logger.Error("Failed to get task metadata from Redis", zap.Error(err))
	} else {
		if err := json.Unmarshal([]byte(metadataJsonStr), &taskMetadata); err != nil {
			f.logger.Error("Failed to unmarshal task metadata", zap.Error(err))
		}
	}

	// grab the trace context from Redis
	tracerJsonStr, err := f.redisClient.Get(ctx, fmt.Sprintf(TaskTraceCtxKey, fuzzlet.TaskId)).Result()
	if err != nil {
		f.logger.Error("Failed to get trace context from Redis", zap.Error(err))
	}
	builderJsonStr, err := f.redisClient.Get(ctx, fmt.Sprintf(BuildTraceCtxKey, fuzzlet.TaskId)).Result()
	if err != nil {
		f.logger.Error("Failed to get build trace context from Redis", zap.Error(err))
	}

	// spawn from global task span, also link with build span
	span := fmt.Sprintf("bandfuzz fuzzing %s", fuzzlet.TaskId)
	fuzzTracer := f.tracerFactory.NewTracerSpawnedWithLink(ctx, tracerJsonStr, []string{builderJsonStr}, span).
		WithAttributes(
			telemetry.NewSpanAttributes(telemetry.Fuzzing).
				WithExtraAttributes(taskMetadata).
				WithTargetHarness(fuzzlet.Harness),
		)
	fuzzTracer.Start()
	defer fuzzTracer.End()

	fuzzCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	fuzzCtx = context.WithValue(fuzzCtx, telemetry.TracerKey{}, fuzzTracer)

	fuzzer, ok := f.fuzzerMap[fuzzlet.FuzzEngine]
	if !ok {
		f.logger.Error("fuzzer not found", zap.String("fuzz_engine", fuzzlet.FuzzEngine))
		return errors.New("fuzzer not found")
	}

	handler, err := fuzzer.RunFuzz(fuzzCtx, fuzzlet, timeout)
	if err != nil {
		f.logger.Error("failed to run fuzzer", zap.Error(err))
		return err
	}

	// route crashes to crash manager
	crashChan, err := handler.ConsumeCrashes()
	if err != nil {
		f.logger.Error("failed to consume crashes", zap.Error(err))
		return err
	}
	f.crashManager.RegisterCrashChan(fuzzCtx, crashChan)

	// route seeds to seed manager
	seedChan, err := handler.ConsumeSeeds()
	if err != nil {
		f.logger.Error("failed to consume seeds", zap.Error(err))
		return err
	}
	f.seedManager.RegisterSeedChan(seedChan)

	// wait until the fuzzer is finished
	handler.BlockUntilFinished()

	return nil
}

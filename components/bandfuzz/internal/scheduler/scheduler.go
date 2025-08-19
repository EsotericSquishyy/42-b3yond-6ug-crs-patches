package scheduler

import (
	"b3fuzz/config"
	"b3fuzz/internal/fuzz"
	"context"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

type Scheduler struct {
	redisClient *redis.Client
	logger      *zap.Logger
	fuzzRunner  *fuzz.FuzzRunner
	picker      *picker

	done chan struct{}
}

type SchedulerParams struct {
	fx.In

	Lc           fx.Lifecycle
	RedisClient  *redis.Client
	Logger       *zap.Logger
	FuzzerRunner *fuzz.FuzzRunner
	AppConfig    *config.AppConfig
}

func NewScheduler(params SchedulerParams) *Scheduler {
	scheduler := &Scheduler{
		params.RedisClient,
		params.Logger,
		params.FuzzerRunner,
		NewPicker(params.AppConfig.SchedulerConfig.SchedulingInterval),
		make(chan struct{}),
	}

	schedulerCtx, cancel := context.WithCancel(context.Background())

	params.Lc.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			go scheduler.start(schedulerCtx)
			return nil
		},
		OnStop: func(ctx context.Context) error {
			cancel()
			<-scheduler.done
			return nil
		},
	})
	return scheduler
}

// starts a loop to step epochs
func (s *Scheduler) start(ctx context.Context) {
	defer close(s.done)
	var err error
	for {
		var delay time.Duration
		if err != nil {
			delay = 10 * time.Second
		}

		select {
		case <-ctx.Done():
			s.logger.Info("scheduler context done, stopping scheduler")
			return
		case <-time.After(delay):
			err = s.stepEpoch(ctx)
		}
	}
}

// run an epoch (blocking)
func (s *Scheduler) stepEpoch(ctx context.Context) error {
	fuzzlets, err := s.getFuzzlets(ctx)
	if err != nil {
		s.logger.Warn("redis fuzzlets key not available, projects are still building", zap.Error(err))
		return err
	}
	if len(fuzzlets) == 0 {
		s.logger.Warn("no fuzzlets available")
		return errors.New("no fuzzlets available")
	}

	fuzzlet, timeout := s.picker.pick(fuzzlets)
	return s.fuzzRunner.RunFuzz(ctx, fuzzlet, timeout)
}

package scheduler

import (
	"context"
	"sync"
	"time"

	"go.uber.org/fx"
	"go.uber.org/zap"
)

// register a routine to be run periodically
type ScheduleRoutine interface {
	Run() error
	Name() string
	Cancel()
}

type SchedulerParams struct {
	fx.In

	Lifecycle fx.Lifecycle
	Logger    *zap.Logger
	Routines  []ScheduleRoutine `group:"routines"`
}

type Scheduler struct {
	logger   *zap.Logger
	shutdown chan struct{}
	routines map[string]ScheduleRoutine
}

func NewScheduler(params SchedulerParams) *Scheduler {
	routines := make(map[string]ScheduleRoutine)

	// Register all routines from the injected group
	for _, routine := range params.Routines {
		routines[routine.Name()] = routine
	}

	scheduler := &Scheduler{
		logger:   params.Logger,
		routines: routines,
		shutdown: make(chan struct{}),
	}

	params.Lifecycle.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			go scheduler.Start()
			return nil
		},
		OnStop: func(ctx context.Context) error {
			close(scheduler.shutdown)
			return nil
		},
	})

	return scheduler
}

func (s *Scheduler) Start() {
	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	// Add a mutex to prevent concurrent processing
	var processing sync.Mutex

	for {
		// Try to acquire the lock, skip if already processing
		if !processing.TryLock() {
			s.logger.Warn("Previous task processing still in progress, skipping this tick")
			continue
		}

		// Release the lock when done
		go func() {
			defer processing.Unlock()
			for _, routine := range s.routines {
				s.logger.Debug("Running routine", zap.String("name", routine.Name()))
				if err := routine.Run(); err != nil {
					s.logger.Error("Failed to run routine", zap.Error(err))
				} else {
					s.logger.Debug("Routine completed", zap.String("name", routine.Name()))
				}
			}
		}()
		select {
		case <-s.shutdown:
			return
		case <-ticker.C:
			continue
		}
	}
}

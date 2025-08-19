package crash

import (
	"b3fuzz/internal/types"
	"b3fuzz/pkg/database"
	"b3fuzz/pkg/telemetry"
	"context"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"go.uber.org/fx"
	"go.uber.org/zap"
	"gorm.io/gorm"
)

type CrashManager struct {
	db     *gorm.DB
	logger *zap.Logger

	crashFolder string
	crashChan   chan types.CrashMessage
	wg          sync.WaitGroup
	done        chan struct{}
}

func NewCrashManager(db *gorm.DB, logger *zap.Logger, lifeCycle fx.Lifecycle) *CrashManager {
	crashFolder := filepath.Join("/crs/b3fuzz/crashes")
	if err := os.MkdirAll(crashFolder, 0755); err != nil {
		// if we can't create the crash folder, there's no point in continueing
		logger.Fatal("failed to create place to crash folder", zap.Error(err))
		return nil
	}

	c := &CrashManager{
		db,
		logger,
		crashFolder,
		make(chan types.CrashMessage, 1024),
		sync.WaitGroup{},
		make(chan struct{}),
	}

	lifeCycle.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			c.logger.Debug("starting crash manager")
			go c.start()
			return nil
		},
		OnStop: func(ctx context.Context) error {
			c.logger.Info("stopping crash manager")
			c.wg.Wait() // wait until all crash channel are properly closed
			c.logger.Debug("closing crash channel")
			close(c.crashChan)
			c.logger.Debug("waiting for crash manager to finish processing")
			<-c.done // wait until all crashes are processed
			return nil
		},
	})

	return c
}

func (c *CrashManager) RegisterCrashChan(ctx context.Context, rCh <-chan types.CrashMessage) {
	c.wg.Add(1)
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	povTracer := tracer.Spawn("POV manager")
	povTracer.Start()
	go func() {
		defer c.wg.Done()
		defer povTracer.End()

		povCounter := 0
		for crash := range rCh {
			povCounter++
			c.logger.Debug("new crash message received", zap.Any("crash", crash))
			c.crashChan <- crash
		}
		c.logger.Debug("crash channel closed")

		povTracer.WithAttributes(telemetry.EmptySpanAttributes().WithExtraAttribute("pov_found", povCounter))
	}()
	c.logger.Debug("new crash channel registered")
}

func (c *CrashManager) start() {
	defer close(c.done)
	for crash := range c.crashChan {
		err := c.processCrashFile(crash)
		if err != nil {
			c.logger.Error("failed to process crash file", zap.Error(err))
			continue
		}
	}
}

// processCrashFile processes a single crash file
func (c *CrashManager) processCrashFile(msg types.CrashMessage) error {
	crashStore := filepath.Join(c.crashFolder, msg.Fuzzlet.TaskId, msg.Fuzzlet.Harness, msg.Fuzzlet.Sanitizer)
	if err := os.MkdirAll(crashStore, 0755); err != nil {
		return fmt.Errorf("failed to create crash store directory: %w", err)
	}

	// Read the crash file and get the md5 hash
	crashData, err := os.ReadFile(msg.CrashFile)
	if err != nil {
		return fmt.Errorf("failed to read crash file: %w", err)
	}
	crashMd5 := md5.Sum(crashData)
	crashPath := filepath.Join(crashStore, hex.EncodeToString(crashMd5[:]))
	err = os.WriteFile(crashPath, crashData, 0644)
	if err != nil {
		return fmt.Errorf("failed to write crash file: %w", err)
	}

	// Create and submit the bug
	bug := database.NewBug(
		msg.Fuzzlet.TaskId,
		crashPath,
		msg.Fuzzlet.Harness,
		msg.Fuzzlet.Sanitizer,
	)

	// Use the global context for database operations
	if err := database.AddBugs(context.Background(), c.db, []*database.Bug{bug}); err != nil {
		return fmt.Errorf("failed to add bug: %w", err)
	}

	return nil
}

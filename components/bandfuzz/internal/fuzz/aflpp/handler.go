package aflpp

import (
	"b3fuzz/internal/types"
	"b3fuzz/pkg/watchdog"
	"context"
	"os"
	"path"
	"path/filepath"
	"sync"
	"time"

	"go.uber.org/zap"
)

type AFLFuzzerHandler struct {
	crashChan     chan types.CrashMessage
	queueChan     chan types.SeedMessage
	crashWatchDog *watchdog.WatchDog
	queueWatchDog *watchdog.WatchDog

	seedsFolder  string
	outputFolder string

	logger       *zap.Logger
	instantCount int

	wg *sync.WaitGroup
}

func (f *AFLFuzzerHandler) ConsumeCrashes() (<-chan types.CrashMessage, error) {
	return f.crashChan, nil
}

func (f *AFLFuzzerHandler) ConsumeSeeds() (<-chan types.SeedMessage, error) {
	return f.queueChan, nil
}

func (f *AFLFuzzerHandler) BlockUntilFinished() {
	f.wg.Wait()
}

// startCrashMonitor periodically scans for new crash directories and adds them to the crash watchdog.
//
// This method runs in a loop, checking every 10 seconds for new "crashes" directories under the output folder.
// When a new crash directory is found, it is added to the crashWatchDog for monitoring.
// The monitor stops when all expected crash directories (equal to instantCount) are being watched or when the context is cancelled.
func (f *AFLFuzzerHandler) startCrashMonitor(fuzzCtx context.Context) {
	crashGlob := path.Join(f.outputFolder, "*", "crashes")
	watched := make(map[string]struct{})

	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-fuzzCtx.Done():
			return
		case <-ticker.C:
			matches, err := filepath.Glob(crashGlob)
			if err != nil {
				f.logger.Error("failed to glob crash folder", zap.Error(err))
			}
			for _, crashDir := range matches {
				if _, err := os.Stat(crashDir); err == nil {
					if _, ok := watched[crashDir]; ok {
						continue
					}
					f.crashWatchDog.AddDir(crashDir)
					f.logger.Debug("added crash folder to watch dog", zap.String("crash_dir", crashDir))
					watched[crashDir] = struct{}{}
				}
			}
			if len(watched) == f.instantCount {
				f.logger.Debug("all crash directories watched, stopping crash monitor")
				return
			}
		}
	}
}

// startQueueMonitor waits for the AFL queue directory to become available and adds it to the queue watchdog.
//
// This method periodically checks (every 10 seconds) for the existence of the "queue" directory
// under the "master" output folder. Once the directory is found, it is added to the queueWatchDog.
// The monitor stops if the context is cancelled.
func (f *AFLFuzzerHandler) startQueueMonitor(fuzzCtx context.Context) {
	queueFolder := path.Join(f.outputFolder, "master", "queue")

	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-fuzzCtx.Done():
			return
		case <-ticker.C:
			if _, err := os.Stat(queueFolder); err == nil {
				f.queueWatchDog.AddDir(queueFolder)
				f.logger.Debug("added queue folder to watch dog", zap.String("queue_dir", queueFolder))
				return
			}
		}
	}
}

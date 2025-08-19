package watchdog

import (
	"context"
	"os"
	"path/filepath"

	"github.com/fsnotify/fsnotify"
	"go.uber.org/zap"
)

type WatchDogFactory struct {
	logger *zap.Logger
}

type filterFun func(string) bool

type WatchDog struct {
	watchCtx   context.Context
	notifyChan chan<- string
	filter     filterFun
	logger     *zap.Logger

	// states
	watcher *fsnotify.Watcher
}

func NewWatchDogFactory(logger *zap.Logger) *WatchDogFactory {
	return &WatchDogFactory{
		logger: logger,
	}
}

// create a new WatchDog to monitor file creation events
//
// - `watchCtx` is the context to control the lifecycle of the watcher. After the context is done, the watcher will stop watching.
//
// - `notifyChan` is a channel to send notifications about file creation events. This can be the crashChan for most fuzzers.
//
// - `filter` is a function to filter the events. If it returns true, the event will be ignored. If set to nil, all events will be sent.
func (w *WatchDogFactory) New(watchCtx context.Context, notifyChan chan<- string, filter filterFun) *WatchDog {
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		w.logger.Fatal("Failed to create watcher", zap.Error(err))
	}

	watchDog := &WatchDog{
		watchCtx,
		notifyChan, // send only channel
		filter,
		w.logger,
		watcher,
	}

	go watchDog.watch()

	return watchDog
}

// add a directory to the watch list
func (w *WatchDog) AddDir(dir string) {
	absDir, err := filepath.Abs(dir)
	if err != nil {
		w.logger.Error("Failed to get absolute path", zap.String("dir", dir), zap.Error(err))
		return
	}
	// check if the directory exists
	if _, err := os.Stat(absDir); os.IsNotExist(err) {
		w.logger.Error("Directory does not exist", zap.String("dir", absDir), zap.Error(err))
		return
	}
	if err := w.watcher.Add(absDir); err != nil {
		w.logger.Error("Failed to add directory to watcher", zap.String("dir", dir), zap.Error(err))
		return
	}
	w.logger.Debug("Added directory to watch list", zap.String("dir", dir))
}

func (w *WatchDog) watch() {
	defer w.watcher.Close()
	defer close(w.notifyChan)
	for {
		select {
		case <-w.watchCtx.Done():
			return
		case event, ok := <-w.watcher.Events:
			if !ok {
				w.logger.Debug("fsnotify channel closed", zap.String("dir", event.Name))
				return
			}
			w.handleEvent(event)
		case err, ok := <-w.watcher.Errors:
			if !ok {
				w.logger.Debug("fsnotify error channel closed", zap.Error(err))
				return
			}
			w.logger.Error("fsnotify error", zap.Error(err))
		}
	}
}

func (w *WatchDog) handleEvent(event fsnotify.Event) {
	w.logger.Debug("fsnotify event", zap.String("event", event.String()))
	if event.Op&fsnotify.Create == fsnotify.Create {
		w.logger.Debug("File created", zap.String("file", event.Name))
		if w.filter == nil || w.filter(event.Name) {
			w.notifyChan <- event.Name
			w.logger.Debug("File added to notify channel", zap.String("file", event.Name))
		} else {
			w.logger.Debug("File ignored by filter", zap.String("file", event.Name))
		}
	}
}

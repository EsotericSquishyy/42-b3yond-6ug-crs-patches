package aflpp

import (
	"b3fuzz/config"
	"b3fuzz/internal/corpus"
	"b3fuzz/internal/dict"
	"b3fuzz/internal/fuzz"
	"b3fuzz/internal/types"
	"b3fuzz/internal/utils"
	"b3fuzz/pkg/telemetry"
	"b3fuzz/pkg/watchdog"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"go.uber.org/fx"
	"go.uber.org/zap"
)

const (
	AFLFuzzerTmpDir       = "/tmp/b3fuzz/afl"
	AFLFuzzerHarnessesDir = "/tmp/b3fuzz/afl/artifacts" // artifacts/<task_id>/<harness>/<engine>/<sanitizer>
)

type AFLFuzzer struct {
	logger        *zap.Logger
	watchDogFac   *watchdog.WatchDogFactory
	corpusGrabber *corpus.CorpusGrabber
	dictGrabber   *dict.DictGrabber
	appConfig     *config.AppConfig
}

type AFLFuzzerParams struct {
	fx.In

	Logger        *zap.Logger
	CorpusGrabber *corpus.CorpusGrabber
	DictGrabber   *dict.DictGrabber
	WatchDogFac   *watchdog.WatchDogFactory
	AppConfig     *config.AppConfig
}

func NewAFLFuzzer(params AFLFuzzerParams) *AFLFuzzer {
	// check if afl-fuzz is correctly installed
	if _, err := exec.LookPath("afl-fuzz"); err != nil {
		params.Logger.Error("afl-fuzz not found", zap.Error(err))
		return nil
	}

	return &AFLFuzzer{
		params.Logger,
		params.WatchDogFac,
		params.CorpusGrabber,
		params.DictGrabber,
		params.AppConfig,
	}
}

func (f *AFLFuzzer) SupportedEngines() []string {
	return []string{"afl", "aflpp", "directed"}
}

func (f *AFLFuzzer) RunFuzz(ctx context.Context, fuzzlet *types.Fuzzlet, timeout time.Duration) (fuzz.FuzzerHandler, error) {
	// Initialize tracer and logger
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	logger := f.logger.With(
		zap.String("task_id", fuzzlet.TaskId),
		zap.String("harness", fuzzlet.Harness),
		zap.String("fuzz_engine", fuzzlet.FuzzEngine),
		zap.String("sanitizer", fuzzlet.Sanitizer),
	)
	startTime := time.Now()

	// Minimize fuzzing I/O latency by copying the harness binary to a local directory
	tracer.AddEvent("fuzzer.afl.prepare_harness", telemetry.EventAttributes{})
	localHarnessPath, err := f.prepareLocalHarness(fuzzlet)
	if err != nil {
		logger.Error("failed to prepare local harness", zap.Error(err))
		return nil, err
	}

	// Create "-i <seedsFolder>" and "-o <outputFolder>" for afl-fuzz
	seedsFolder, outputFolder, err := f.prepareDirs(fuzzlet)
	if err != nil {
		logger.Error("failed to prepare directories", zap.Error(err))
		return nil, err
	}

	// Copy existing seeds to seedsFolder
	tracer.AddEvent("fuzzer.afl.prepare_seeds", telemetry.EventAttributes{})
	if err := f.corpusGrabber.CollectCorpusToDir(ctx, fuzzlet.TaskId, fuzzlet.Harness, seedsFolder); err != nil {
		logger.Error("failed to grab seeds", zap.Error(err))
	}

	// Merge existing dict to a local temporary path
	tracer.AddEvent("fuzzer.afl.prepare_dicts", telemetry.EventAttributes{})
	dictPath, err := f.dictGrabber.GrabDict(ctx, fuzzlet.TaskId, fuzzlet.Harness)
	if err != nil {
		logger.Error("failed to grab dict, will not use it", zap.Error(err))
	}

	aflWaitGroup := &sync.WaitGroup{}

	// Calculate the graceful shutdown timeout
	// This is the time we give AFL to finish processing before we kill it.
	deadline := startTime.Add(timeout)
	remaining := time.Until(deadline)
	gracefulTimeout := time.Duration(float64(remaining) * 0.9)

	// start master mode afl-fuzz
	tracer.AddEvent("fuzzer.afl.start", telemetry.EventAttributes{})

	masterAflInstance := &AFLInstance{
		"master",
		AFLMaster,
		seedsFolder,
		outputFolder,
		dictPath,
		5000, // default timeout of 5 seconds
		localHarnessPath,
		masterAFLEnv(),
		logger,
	}

	aflWaitGroup.Add(1)
	go func() {
		defer aflWaitGroup.Done()
		masterAflInstance.Fuzz(ctx, gracefulTimeout)
	}()

	// start multiple afl-fuzz instances in slave mode
	for slaveIdx := range f.appConfig.CoreCount - 1 {
		slaveAflInstance := &AFLInstance{
			fmt.Sprintf("slave_%d", slaveIdx),
			AFLSlave,
			seedsFolder,
			outputFolder,
			dictPath,
			5000, // default timeout of 5 seconds
			localHarnessPath,
			defaultAFLEnv(),
			logger,
		}

		aflWaitGroup.Add(1)
		go func() {
			defer aflWaitGroup.Done()
			slaveAflInstance.Fuzz(ctx, gracefulTimeout)
		}()
	}

	crashFileNotifyChan := make(chan string, 1024)
	crashChan := make(chan types.CrashMessage, 1024)
	go f.crashProxy(ctx, fuzzlet, crashFileNotifyChan, crashChan)

	queueFileNotifyChan := make(chan string, 1024)
	queueChan := make(chan types.SeedMessage, 1024)
	go f.seedProxy(fuzzlet, queueFileNotifyChan, queueChan)

	handler := &AFLFuzzerHandler{
		crashChan,
		queueChan,
		f.watchDogFac.New(ctx, crashFileNotifyChan, filterCrashFiles),
		f.watchDogFac.New(ctx, queueFileNotifyChan, filterQueueFiles),
		seedsFolder,
		outputFolder,
		logger,
		f.appConfig.CoreCount,
		aflWaitGroup,
	}
	go handler.startCrashMonitor(ctx)
	go handler.startQueueMonitor(ctx)

	return handler, nil
}

// filterCrashFiles filters out files that are not crashes but are in the crash folder
func filterCrashFiles(crashFileName string) bool {
	crashBaseName := path.Base(crashFileName)
	return crashBaseName != "README.txt"
}

// filterCrashFiles filters out files that are not crashes but are in the crash folder
func filterQueueFiles(seedFileName string) bool {
	seedBaseName := path.Base(seedFileName)
	return !strings.Contains(seedBaseName, "orig:")
}

// crashProxy listens for crash file notifications and forwards crash messages.
//
// It receives crash file paths from fileNotifyChan, constructs CrashMessage objects
// with the provided fuzzlet, and sends them to crashChan. On the first crash found,
// it emits a "first_pov_found" event using the provided telemetry tracer.
func (f *AFLFuzzer) crashProxy(ctx context.Context, fuzzlet *types.Fuzzlet, fileNotifyChan <-chan string, crashChan chan<- types.CrashMessage) {
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	defer close(crashChan)

	ever_found := false
	for crashFile := range fileNotifyChan {
		crashMsg := types.CrashMessage{
			CrashFile: crashFile,
			Fuzzlet:   fuzzlet,
		}
		crashChan <- crashMsg
		if !ever_found {
			tracer.AddEvent("first_pov_found",
				telemetry.NewEventAttributes(map[string]string{
					"pov_name": filepath.Base(crashFile),
				}))
			ever_found = true
		}
	}
}

// seedProxy listens for new seed file notifications and forwards seed messages.
//
// It receives seed file paths from fileNotifyChan, constructs SeedMessage objects
// with the provided fuzzlet, and sends them to seedChan.
func (f *AFLFuzzer) seedProxy(fuzzlet *types.Fuzzlet, fileNotifyChan <-chan string, seedChan chan<- types.SeedMessage) {
	defer close(seedChan)
	for seedFile := range fileNotifyChan {
		seedMsg := types.SeedMessage{
			SeedFile: seedFile,
			Fuzzlet:  fuzzlet,
		}
		seedChan <- seedMsg
	}
}

// prepareLocalHarness copies the fuzz harness binary from the shared artifact path
// to a local temporary directory specific to the fuzzing task. It ensures the
// destination directory exists and returns the local path to the copied harness.
// Returns an error if directory creation or file copying fails.
func (f *AFLFuzzer) prepareLocalHarness(fuzzlet *types.Fuzzlet) (string, error) {
	harnessSharedPath := fuzzlet.ArtifactPath
	binaryName := path.Base(harnessSharedPath)
	harnessLocalPath := path.Join(AFLFuzzerTmpDir, fuzzlet.TaskId, fuzzlet.Harness, fuzzlet.Sanitizer, binaryName)
	if err := os.MkdirAll(path.Dir(harnessLocalPath), 0755); err != nil {
		return "", err
	}
	if err := utils.CopyFile(harnessSharedPath, harnessLocalPath); err != nil {
		return "", err
	}
	return harnessLocalPath, nil
}

// prepareDirs creates the necessary directories for AFL fuzzing: the seeds folder
// and the output folder. The paths are constructed based on the fuzzlet's TaskId,
// Harness, and Sanitizer. Returns the paths to the seeds and output folders, or an
// error if directory creation fails.
func (f *AFLFuzzer) prepareDirs(fuzzlet *types.Fuzzlet) (seedsFolder, outputFolder string, err error) {
	seedsFolder = path.Join(AFLFuzzerTmpDir, fuzzlet.TaskId, fuzzlet.Harness, "seeds")
	outputFolder = path.Join(AFLFuzzerTmpDir, fuzzlet.TaskId, fuzzlet.Harness, fuzzlet.Sanitizer, "output")
	for _, dir := range []string{seedsFolder, outputFolder} {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return "", "", err
		}
	}
	return seedsFolder, outputFolder, nil
}

var AFLModule = fx.Options(
	fx.Provide(fx.Annotate(NewAFLFuzzer, fx.As(new(fuzz.Fuzzer)), fx.ResultTags(`group:"fuzzers"`))),
)

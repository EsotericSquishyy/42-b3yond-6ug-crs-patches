package aflpp

import (
	"b3fuzz/pkg/telemetry"
	"bufio"
	"bytes"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"strings"
	"syscall"
	"time"

	"go.opentelemetry.io/otel/codes"
	"go.uber.org/zap"
)

// --- AFLInstance ---
type AFLInstance struct {
	Name      string          // name of the instance
	Mode      AFLInstanceMode // master or slave
	InputDir  string          // -i <inputDir>
	OutputDir string          // -o <outputDir>
	DictPath  string          // path to the dictionary file, if any
	Timeout   int             // timeout in ms for each fuzzing iteration
	Harness   string          // path to the harness binary
	Env       []string        // environment variables to set for the afl-fuzz process

	logger *zap.Logger // logger for the instance
}

type AFLInstanceMode int

const (
	AFLMaster AFLInstanceMode = iota // Master mode for AFL
	AFLSlave                         // Slave mode for AFL
)

// Fuzz launches the AFL fuzzing process and blocks until it exits, the
// timeout is reached, or the context is cancelled. Behavior is as follows:
//
//  1. Starts “afl-fuzz” with the instance’s args and environment.
//  2. If the process exits before `timeout`, returns immediately.
//  3. If the `timeout` elapses, sends a SIGINT to request graceful shutdown,
//     then waits for the process to exit or for `ctx` to be done.
//  4. If `ctx` is cancelled at any time, the CommandContext ensures the
//     process is killed (SIGKILL).
//
// Guarantees that the process will not be left running once this method returns.
func (m AFLInstance) Fuzz(ctx context.Context, timeout time.Duration) {
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	aflTracer := tracer.Spawn("running AFL++")
	aflTracer.Start()
	defer aflTracer.End()

	m.fuzz(ctx, timeout)

	// check `fuzzer_stats` file for AFL++ statistics
	fuzzerStatsPath := path.Join(m.OutputDir, m.Name, "fuzzer_stats")
	data, err := os.ReadFile(fuzzerStatsPath)
	if err != nil {
		aflTracer.SetStatus(codes.Error, "failed to read fuzzer stats")
		m.logger.Error("failed to read fuzzer stats", zap.Error(err))
		return
	}

	attrs, err := parseFuzzerStats(bytes.NewReader(data), m.logger)
	if err != nil {
		m.logger.Error("failed to parse fuzzer stats", zap.Error(err))
		return
	}
	aflTracer.WithAttributes(attrs)
}

// parseFuzzerStats reads from r line by line, expecting "key: value" pairs.
// Returns an error only if an unexpected I/O error occurs.
func parseFuzzerStats(r io.Reader, logger *zap.Logger) (*telemetry.SpanAttributes, error) {
	attrs := telemetry.EmptySpanAttributes()
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue // skip empty lines
		}
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		rawKey := strings.TrimSpace(parts[0])
		rawValue := strings.TrimSpace(parts[1])

		logger.Debug("parsed fuzzer stat", zap.String("key", rawKey), zap.String("value", rawValue))

		key := "fuzzer.afl." + rawKey
		attrs = attrs.WithExtraAttribute(key, rawValue)
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("scanner error: %w", err)
	}
	return attrs, nil
}

func (m AFLInstance) fuzz(ctx context.Context, timeout time.Duration) {
	cmd := exec.CommandContext(ctx, "afl-fuzz", m.buildArgs()...)
	cmd.Env = append(os.Environ(), m.Env...)

	// Channel to observe when the process exits
	done := make(chan struct{})
	go func() {
		m.logger.Info("running afl-fuzz", zap.String("command", cmd.String()))
		_ = cmd.Run() // ignore error; process exit is signaled via channel
		close(done)
	}()

	// Timer for graceful-shutdown window
	timer := time.NewTicker(timeout)
	defer timer.Stop()

	select {
	case <-done:
		// Process exited on its own
		return

	case <-timer.C:
		// Timeout reached → request graceful shutdown
		if cmd.Process != nil {
			// Best‐effort send SIGINT
			_ = cmd.Process.Signal(syscall.SIGINT)
		}
		// After SIGINT, wait for exit or context cancellation
		select {
		case <-done:
			return
		case <-ctx.Done():
			return
		}

	case <-ctx.Done():
		// Context cancelled → process is killed by CommandContext
		return
	}
}

// buildArgs builds the command line arguments for the afl-fuzz instance based on its configuration.
func (m AFLInstance) buildArgs() []string {
	// Input & Output
	args := []string{"-i", m.InputDir, "-o", m.OutputDir}

	// Mode & Name
	switch m.Mode {
	case AFLMaster:
		args = append(args, "-M", m.Name)
	case AFLSlave:
		args = append(args, "-S", m.Name)
	}

	// Timeout
	if m.Timeout <= 0 {
		m.Timeout = 5000 // default timeout of 5 seconds
	}
	args = append(args, "-t", fmt.Sprintf("%d+", m.Timeout))

	// Dict
	if m.DictPath != "" {
		args = append(args, "-x", m.DictPath)
	}

	// Harness
	args = append(args, "--", m.Harness) // recommend way to run harness with AFL++ driver
	return args
}

func defaultAFLEnv() []string {
	return []string{
		"AFL_NO_UI=1",
		"AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1",
		"AFL_SKIP_CPUFREQ=1",
		"AFL_TRY_AFFINITY=1",
		"AFL_FAST_CAL=1",
		"AFL_CMPLOG_ONLY_NEW=1",
		"AFL_FORKSRV_INIT_TMOUT=30000",
		"AFL_IGNORE_PROBLEMS=1",      // do not terminate fuzzing
		"AFL_IGNORE_SEED_PROBLEMS=1", // skip over crashes and timeouts in the seeds instead of exiting
		"AFL_IGNORE_UNKNOWN_ENVS=1",  // disable unknown env warnings
	}
}

// Master mode specific environment variables
func masterAFLEnv() []string {
	// setting AFL_FINAL_SYNC to perform a final import of test cases when terminating.
	// This is beneficial for -M main fuzzers to ensure it has all unique test cases
	// and hence you only need to afl-cmin this single queue.
	return append(defaultAFLEnv(), "AFL_FINAL_SYNC=1")
}

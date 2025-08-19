package fuzz

import (
	"b3fuzz/internal/types"
	"context"
	"time"
)

// Fuzzer describes the interface for different fuzzers
type Fuzzer interface {
	// Run the fuzzer with given fuzzlet.
	//
	// Fuzzing is expected to finish *before* the timeout.
	// If not, fuzzing must be killed when the context is done.
	// Related resources in FuzzerHanlder should also be closed.
	RunFuzz(ctx context.Context, fuzzlet *types.Fuzzlet, timeout time.Duration) (FuzzerHandler, error)
	SupportedEngines() []string
}

// FuzzerHandler describes the interface for managing fuzzing instances and handling fuzzing results.
type FuzzerHandler interface {
	// return two channels for new crashes / seeds.
	// The channel is owned by the handler, and will be closed when
	// (1) it is believed no more crash or seeds will show up, or
	// (2) context passed to RunFuzz is done.
	ConsumeCrashes() (<-chan types.CrashMessage, error)
	ConsumeSeeds() (<-chan types.SeedMessage, error)

	// blocks until
	// (1) it is believed all fuzzing resources are properly shutdown, or
	// (2) context passed to RunFuzz is done.
	BlockUntilFinished()
}

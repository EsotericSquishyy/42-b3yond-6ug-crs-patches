package fuzz

import (
	"b3fuzz/internal/types"
	"context"
	"errors"
)

type LibFuzzer struct{}

// LibFuzzer support is not planned yet
// This function exists to test if dependencies injection works
func NewLibFuzzer() *LibFuzzer {
	return nil
}

func (m *LibFuzzer) SupportedEngines() []string {
	return []string{"libfuzzer"}
}

func (m *LibFuzzer) RunFuzz(ctx context.Context, fuzzlet *types.Fuzzlet) (FuzzerHandler, error) {
	return nil, errors.New("libfuzzer is not supported yet")
}

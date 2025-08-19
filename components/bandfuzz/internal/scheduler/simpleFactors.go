package scheduler

import "b3fuzz/internal/types"

// TaskFactor takes the "task" into account
// For different tasks, we can have different number of fuzzlets
// But we assume that the number of bugs balanced across tasks
// So, TaskFactor returns a score based on the number of fuzzlets in current task
type TaskFactor struct{}

func (tf *TaskFactor) Score(fuzzlets []*types.Fuzzlet) []float64 {
	// group fuzzlets by task
	fuzzletsByTask := make(map[string][]*types.Fuzzlet)
	for _, fuzzlet := range fuzzlets {
		fuzzletsByTask[fuzzlet.TaskId] = append(fuzzletsByTask[fuzzlet.TaskId], fuzzlet)
	}

	score := make([]float64, len(fuzzlets))
	// calculate score for each fuzzlet based on the number of fuzzlets in the same task
	for idx, fuzzlet := range fuzzlets {
		sameTaskFuzzletsCnt := len(fuzzletsByTask[fuzzlet.TaskId])
		if sameTaskFuzzletsCnt == 0 {
			// this fuzzlet is not in any task, so we give it a score of 0
			// this should not happen, but just in case
			score[idx] = 0
		}
		score[idx] = 1 / float64(sameTaskFuzzletsCnt)
	}

	return score
}

// SanitizerFactor takes the "sanitizer" into account
// ASAN is important, UBSAN and MSAN are less important
type SanitizerFactor struct{}

func (sf *SanitizerFactor) Score(fuzzlets []*types.Fuzzlet) []float64 {
	score := make([]float64, len(fuzzlets))
	for idx, fuzzlet := range fuzzlets {
		switch fuzzlet.Sanitizer {
		case "address":
			score[idx] = 5
		case "undefined":
			score[idx] = 1
		case "memory":
			score[idx] = 1
		default:
			score[idx] = 1
		}
	}
	return score
}

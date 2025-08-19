package scheduler

import (
	"b3fuzz/internal/types"
	"math/rand"
	"time"
)

// We are going to score the fuzzlets based on many factors
// Each factor implmenets a Score() method and a Weight() method
// The Score() method returns scores for the fuzzlet based on the factor
type factor interface {
	Score(fuzzlets []*types.Fuzzlet) []float64
}

type picker struct {
	weightedFactors    map[factor]float64
	schedulingInterval time.Duration
}

func NewPicker(schedulingInterval time.Duration) *picker {
	weightedFactors := make(map[factor]float64)
	weightedFactors[&TaskFactor{}] = 1.0
	weightedFactors[&SanitizerFactor{}] = 1.0

	return &picker{weightedFactors, schedulingInterval}
}

func (p *picker) pick(fuzzlets []*types.Fuzzlet) (*types.Fuzzlet, time.Duration) {
	finalScores := make([]float64, len(fuzzlets))

	for f, weight := range p.weightedFactors {
		scores := f.Score(fuzzlets)
		balancedScores := balance(scores)
		for i, score := range balancedScores {
			finalScores[i] += score * weight
		}
	}

	// Normalize the final scores
	normalScores := balance(finalScores)

	// Pick a fuzzlet based on the normalized scores
	// Sample a random number between 0 and 1
	// Then pick a fuzzlet based on the normalized scores

	randomNum := rand.Float64()
	cumulativeScore := 0.0
	for i, score := range normalScores {
		cumulativeScore += score
		if randomNum <= cumulativeScore {
			return fuzzlets[i], p.schedulingInterval
		}
	}
	// If we reach here, it means we didn't pick any fuzzlet
	// This should not happen, but just in case
	// We can pick a random fuzzlet
	return fuzzlets[rand.Intn(len(fuzzlets))], p.schedulingInterval
}

// a helper function to return a group of balanced score
func balance(ubScore []float64) []float64 {
	balancedScore := make([]float64, len(ubScore))
	sum := 0.0
	for _, score := range ubScore {
		sum += score
	}
	for idx, score := range ubScore {
		balancedScore[idx] = score / sum
	}
	return balancedScore
}

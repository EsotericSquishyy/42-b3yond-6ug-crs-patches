package telemetry

type ActionCategory int

const (
	StaticAnalysis = iota
	DynamicAnalysis
	Fuzzing
	ProgramAnalysis
	Building
	InputGeneration
	PatchGeneration
	Testing
	ScoringSubmission
)

func (a ActionCategory) String() string {
	switch a {
	case StaticAnalysis:
		return "static_analysis"
	case DynamicAnalysis:
		return "dynamic_analysis"
	case Fuzzing:
		return "fuzzing"
	case ProgramAnalysis:
		return "program_analysis"
	case Building:
		return "building"
	case InputGeneration:
		return "input_generation"
	case PatchGeneration:
		return "patch_generation"
	case Testing:
		return "testing"
	case ScoringSubmission:
		return "scoring_submission"
	default:
		return "unknown"
	}
}

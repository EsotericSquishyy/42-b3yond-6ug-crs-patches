package types

// small, self-contained fuzzing unit
type Fuzzlet struct {
	TaskId       string `json:"task_id"`
	Harness      string `json:"harness"`
	Sanitizer    string `json:"sanitizer"`
	FuzzEngine   string `json:"fuzz_engine"`
	ArtifactPath string `json:"artifact_path"`
}

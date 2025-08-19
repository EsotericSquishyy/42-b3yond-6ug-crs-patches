package types

type CrashMessage struct {
	CrashFile string // path to the crash file on local filesystem
	Fuzzlet   *Fuzzlet
}

type SeedMessage struct {
	SeedFile string
	Fuzzlet  *Fuzzlet
}

type CminMessage struct {
	TaskId       string `json:"task_id"`
	Harness      string `json:"harness"`
	SeedBlobPath string `json:"seeds"`
}

package corpus

import (
	"go.uber.org/fx"
)

type Grabber interface {
	// grab the seeds for given (task id, harness) pair. It should always return a path to a tar.gz file
	GrabCorpusBlob(taskId, harness string) (string, error)
}

var CorpusGrabbersModule = fx.Options(
	fx.Provide(NewCorpusGrabber),
	fx.Provide(NewCminSeedGrabber),
	fx.Provide(NewRandomSeedGrabber),
	fx.Provide(NewDBSeedGrabber),
	fx.Provide(NewLibCminCorpusGrabber),
)

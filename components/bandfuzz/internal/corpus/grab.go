package corpus

import (
	"b3fuzz/internal/utils"
	"b3fuzz/pkg/telemetry"
	"context"
	"errors"
	"fmt"
	"os"
	"reflect"

	"go.uber.org/fx"
	"go.uber.org/zap"
)

type CorpusGrabber struct {
	grabbers []Grabber
	logger   *zap.Logger
}

type CorpusGrabberParams struct {
	fx.In

	Logger               *zap.Logger
	CminSeedGrabber      *CminSeedGrabber
	DBSeedGrabber        *DBSeedGrabber
	MockSeedGrabber      *RandomSeedGrabber
	LibCminCorpusGrabber *LibCminCorpusGrabber
}

func NewCorpusGrabber(params CorpusGrabberParams) *CorpusGrabber {
	return &CorpusGrabber{
		grabbers: []Grabber{
			params.LibCminCorpusGrabber,
			params.DBSeedGrabber,
			params.CminSeedGrabber,
			params.MockSeedGrabber,
		},
		logger: params.Logger,
	}
}

func (s *CorpusGrabber) getCorpusBlob(ctx context.Context, taskId, harness string) (string, error) {
	for _, grabber := range s.grabbers {
		if grabber == nil || reflect.ValueOf(grabber).IsNil() {
			s.logger.Warn("one seed grabber is nil")
			continue // skip nil grabbers
		}
		corpusTar, err := s.getCorpusBlobFrom(ctx, taskId, harness, grabber)
		if err == nil {
			return corpusTar, nil
		}
	}
	return "", errors.New("no corpus available")
}

func (s *CorpusGrabber) getCorpusBlobFrom(ctx context.Context, taskId, harness string, grabber Grabber) (string, error) {
	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	grabberSpan := fmt.Sprintf("syncing corpus from %s", reflect.ValueOf(grabber).String())
	grabberTracer := tracer.Spawn(grabberSpan)
	grabberTracer.Start()
	defer grabberTracer.End()

	corpusTar, err := grabber.GrabCorpusBlob(taskId, harness)
	if err != nil {
		s.logger.Warn("failed to grab corpus",
			zap.String("grabber", reflect.ValueOf(grabber).String()),
			zap.String("taskId", taskId),
			zap.String("harness", harness),
			zap.Error(err))
		grabberTracer.AddEvent("failed_to_grab_corpus", telemetry.EventAttributes{})
		return "", fmt.Errorf("failed to grab corpus: %w", err)
	}

	s.logger.Info("grabbed corpus",
		zap.String("grabber", reflect.ValueOf(grabber).String()),
		zap.String("taskId", taskId),
		zap.String("harness", harness))
	return corpusTar, nil
}

func (s *CorpusGrabber) CollectCorpusToDir(ctx context.Context, taskId, harness, dir string) error {
	if _, err := os.Stat(dir); err != nil {
		s.logger.Error("failed to find corpus folder",
			zap.String("taskId", taskId),
			zap.String("harness", harness),
			zap.String("corpus_folder", dir),
			zap.Error(err))
		return err
	}

	tracer := ctx.Value(telemetry.TracerKey{}).(telemetry.Tracer)
	corpusTracer := tracer.Spawn("syncing corpus")
	corpusTracer.Start()
	defer corpusTracer.End()
	collectorCtx := context.WithValue(ctx, telemetry.TracerKey{}, corpusTracer)

	corpusBolb, err := s.getCorpusBlob(collectorCtx, taskId, harness)
	if err != nil {
		return err
	}

	// unpack corpus tar file to corpus folder (flat)
	if err := utils.UnpackTarGz(corpusBolb, dir); err != nil {
		s.logger.Error("failed to unpack corpus tar file",
			zap.String("taskId", taskId),
			zap.String("harness", harness),
			zap.String("corpus_folder", dir),
			zap.Error(err))
		return err
	}

	// how many seeds are there in the corpus?
	files, err := os.ReadDir(dir)
	if err != nil {
		s.logger.Error("failed to read corpus folder",
			zap.String("taskId", taskId),
			zap.String("harness", harness),
			zap.String("corpus_folder", dir),
			zap.Error(err))
	}
	s.logger.Info("successfully get corpus for fuzzing",
		zap.String("taskId", taskId),
		zap.String("harness", harness),
		zap.String("corpus_folder", dir),
		zap.Int("seed_count", len(files)))

	corpusTracer.WithAttributes(
		telemetry.EmptySpanAttributes().WithCorpusSize(len(files)),
	)

	return nil
}

package corpus

import (
	"b3fuzz/internal/utils"
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"go.uber.org/fx"
	"go.uber.org/zap"
	"gorm.io/gorm"
)

type DBSeedGrabber struct {
	db             *gorm.DB
	logger         *zap.Logger
	seedGrabberCtx context.Context
}

func NewDBSeedGrabber(db *gorm.DB, logger *zap.Logger, lifeCycle fx.Lifecycle) *DBSeedGrabber {
	seedGrabberCtx, cancel := context.WithCancel(context.Background())
	lifeCycle.Append(fx.Hook{
		OnStop: func(ctx context.Context) error {
			cancel()
			return nil
		},
	})
	return &DBSeedGrabber{
		db,
		logger,
		seedGrabberCtx,
	}
}

func (s *DBSeedGrabber) GrabCorpusBlob(taskId, harness string) (string, error) {
	var paths []string

	rawSQL := `
(
  SELECT path
  FROM public.seeds
  WHERE
    task_id = @taskID
    AND (harness_name = @harness OR harness_name = '*')
    AND fuzzer IN ('seedgen', 'seedmini', 'corpus', 'seedmcp', 'seedcodex')
)
UNION ALL
(
  SELECT path
  FROM public.seeds
  WHERE
    task_id = @taskID
    AND harness_name = @harness
    AND fuzzer = 'general'
  ORDER BY created_at DESC
  LIMIT 10
)
	`

	err := s.db.Raw(rawSQL,
		sql.Named("taskID", taskId),
		sql.Named("harness", harness),
	).Scan(&paths).Error
	if err != nil {
		return "", err
	}

	if len(paths) == 0 {
		s.logger.Info("No seeds found in db", zap.String("taskId", taskId), zap.String("harness", harness))
		return "", errors.New("no seeds found in database")
	}

	wholeBlob := filepath.Join("/tmp/b3fuzz/dbseeds", taskId, harness)
	tarFilePath := filepath.Join("/tmp/b3fuzz/dbseeds", fmt.Sprintf("%s_%s_seeds.tar.gz", taskId, harness))
	if err := os.MkdirAll(wholeBlob, 0755); err != nil {
		return "", fmt.Errorf("failed to create directory: %w", err)
	}

	// for each path, uncompress the tar file to the wholeBlob directory
	// and then compress the wholeBlob directory to the tarFilePath
	for _, path := range paths {
		if err := utils.UnpackTarGz(path, wholeBlob); err != nil {
			s.logger.Error("Failed to unpack tar file", zap.String("path", path), zap.Error(err))
			continue
		}
	}
	if err := utils.CompressTarGz(wholeBlob, tarFilePath); err != nil {
		return "", fmt.Errorf("failed to create tar file: %w", err)
	}

	s.logger.Info("Got seeds in db", zap.String("taskId", taskId), zap.String("harness", harness))

	return tarFilePath, nil
}

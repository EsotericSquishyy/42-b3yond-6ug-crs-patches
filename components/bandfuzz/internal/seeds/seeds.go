package seeds

import (
	"b3fuzz/internal/types"
	"b3fuzz/internal/utils"
	"b3fuzz/pkg/database"
	"b3fuzz/pkg/mq"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/google/uuid"
	amqp "github.com/rabbitmq/amqp091-go"
	"go.uber.org/fx"
	"go.uber.org/zap"
	"gorm.io/gorm"
)

type SeedManager struct {
	rabbitMQ mq.RabbitMQ
	db       *gorm.DB
	logger   *zap.Logger

	seedFolder string
	seedChan   chan types.SeedMessage
	seedChanWg sync.WaitGroup
}

const (
	CminQueueName = "cmin_queue"
)

func NewSeedManager(rabbitMQ mq.RabbitMQ, db *gorm.DB, logger *zap.Logger, lifeCycle fx.Lifecycle) *SeedManager {
	seedFolder := filepath.Join("/crs/b3fuzz/seeds")
	if err := os.MkdirAll(seedFolder, 0755); err != nil {
		// if we can't create the crash folder, there's no point in continueing
		logger.Fatal("failed to create place to seed folder", zap.Error(err))
		return nil
	}

	s := &SeedManager{
		rabbitMQ,
		db,
		logger,
		seedFolder,
		make(chan types.SeedMessage, 1024),
		sync.WaitGroup{},
	}

	lifeCycle.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			s.logger.Debug("starting seed manager")
			if err := s.declareCminQueue(); err != nil {
				s.logger.Fatal("failed to declare cmin queue", zap.Error(err))
				return err
			}
			go s.start()
			return nil
		},
		OnStop: func(ctx context.Context) error {
			s.logger.Debug("stopping seed manager")
			s.seedChanWg.Wait() // wait until all seed channel are properly closed
			close(s.seedChan)
			return nil
		},
	})

	return s
}

func (s *SeedManager) declareCminQueue() error {
	// declare the cmin queue
	channel := s.rabbitMQ.GetChannel()
	defer channel.Close()
	_, err := channel.QueueDeclare(
		CminQueueName,
		true,
		false,
		false,
		false,
		nil,
	)
	if err != nil {
		return err
	}
	return nil
}

// Route the messages in a seed message channel to the fan-in channel
func (s *SeedManager) RegisterSeedChan(rCh <-chan types.SeedMessage) {
	s.seedChanWg.Add(1)
	go func() {
		defer s.seedChanWg.Done()
		for seed := range rCh {
			s.seedChan <- seed
		}
	}()
}

func (s *SeedManager) start() {
	const batchSize = 1024
	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	batch := make([]types.SeedMessage, 0, batchSize)

	for {
		select {
		case seed, ok := <-s.seedChan:
			if !ok {
				// channel closed: flush any remaining seeds, then exit
				if len(batch) > 0 {
					s.processSeedMessages(batch)
				}
				return
			}
			// accumulate
			batch = append(batch, seed)

			// threshold reached: flush immediately
			if len(batch) >= batchSize {
				s.processSeedMessages(batch)
				batch = batch[:0]
			}

		case <-ticker.C:
			// timer fired: flush whatever we have
			if len(batch) > 0 {
				s.processSeedMessages(batch)
				batch = batch[:0]
			}
		}
	}
}

type TaskHarness struct {
	taskID  string
	harness string
}

func (s *SeedManager) processSeedMessages(msgs []types.SeedMessage) error {
	// group the seeds by (taskID, harness) pair
	harnessSeeds := make(map[TaskHarness][]string)
	for _, msg := range msgs {
		if msg.Fuzzlet == nil {
			s.logger.Fatal("fuzzlet in message is Nil")
		}
		taskHarness := TaskHarness{msg.Fuzzlet.TaskId, msg.Fuzzlet.Harness}
		harnessSeeds[taskHarness] = append(harnessSeeds[taskHarness], msg.SeedFile)
	}

	wg := sync.WaitGroup{}

	// for each (taskID, harness) pair, create a new seed bundle
	for taskHarness, seeds := range harnessSeeds {
		wg.Add(1)

		go func(taskHarness TaskHarness, seeds []string) {
			defer wg.Done()
			s.logger.Debug("processing seed messages",
				zap.String("task_id", taskHarness.taskID),
				zap.String("harness", taskHarness.harness),
				zap.Int("seeds_count", len(seeds)))
			// use a tmp folder to collect the seeds together
			tmpDir, err := os.MkdirTemp("", "seed-bundle-*")
			if err != nil {
				s.logger.Error("failed to create tmp dir for seed bundle", zap.Error(err))
				return
			}
			defer os.RemoveAll(tmpDir)

			// copy the seeds to the tmp dir, rename them using UUID
			for _, seed := range seeds {
				utils.CopyFile(seed, filepath.Join(tmpDir, uuid.New().String()))
			}

			bundleName := taskHarness.harness + "-" + uuid.New().String() + ".tar.gz"
			bundlePath := filepath.Join(s.seedFolder, bundleName)
			if err := utils.CompressTarGz(tmpDir, bundlePath); err != nil {
				s.logger.Error("failed to create seed bundle", zap.Error(err))
				return
			}

			// craft a CminMessage
			cminMsg := types.CminMessage{
				TaskId:       taskHarness.taskID,
				Harness:      taskHarness.harness,
				SeedBlobPath: bundlePath,
			}
			cminMsgBytes, err := json.Marshal(cminMsg)
			if err != nil {
				s.logger.Error("failed to marshal CminMessage to JSON", zap.Error(err), zap.Any("cminMsg", cminMsg))
				return
			}

			// send the CminMessage to the cmin queue
			channel := s.rabbitMQ.GetChannel()
			defer channel.Close()
			channel.Publish(
				"",
				CminQueueName,
				false,
				false,
				amqp.Publishing{
					ContentType: "application/json",
					Body:        cminMsgBytes,
				},
			)

			// send the seed blob to database
			hostname, _ := os.Hostname()
			seedEntry := database.NewSeed(
				taskHarness.taskID,
				bundlePath,
				taskHarness.harness,
				database.GeneralFuzz,
				hostname,
				0,
				database.Metric{})
			if err := s.db.Create(seedEntry).Error; err != nil {
				s.logger.Error("failed to save seeds to database", zap.Error(err), zap.Any("seeds", seeds))
				return
			}
		}(taskHarness, seeds)
	}

	wg.Wait()
	return nil
}

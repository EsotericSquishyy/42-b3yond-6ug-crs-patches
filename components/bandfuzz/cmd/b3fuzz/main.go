package main

import (
	"b3fuzz/config"
	"b3fuzz/internal/corpus"
	"b3fuzz/internal/crash"
	"b3fuzz/internal/dict"
	"b3fuzz/internal/fuzz"
	"b3fuzz/internal/fuzz/aflpp"
	"b3fuzz/internal/scheduler"
	"b3fuzz/internal/seeds"
	"b3fuzz/pkg/database"
	"b3fuzz/pkg/logger"
	"b3fuzz/pkg/mq"
	"b3fuzz/pkg/telemetry"
	"b3fuzz/pkg/watchdog"
	"os/exec"

	_ "go.uber.org/automaxprocs"
	"go.uber.org/fx"
	"go.uber.org/fx/fxevent"
	"go.uber.org/zap"
)

func setUpMmapRNDBits(logger *zap.Logger) {
	// Set the mmap_rnd_bits to 28 to avoid ASLR issues on ASAN
	if err := exec.Command("sysctl", "-w", "vm.mmap_rnd_bits=28").Run(); err != nil {
		logger.Warn("Failed to set mmap_rnd_bits", zap.Error(err))
	} else {
		logger.Info("Successfully set mmap_rnd_bits to 28")
	}
}

func main() {
	app := fx.New(
		fx.Provide(
			config.LoadConfig,           // inject config
			database.NewDBConnection,    // inject db connection
			database.NewRedisClient,     // inject redis client
			logger.NewLogger,            // inject logger
			mq.NewRabbitMQ,              // inject rabbitmq service
			telemetry.NewTelemetry,      // inject telemetry
			telemetry.NewTracerFactory,  // inject telemetry tracer factory
			fuzz.NewFuzzRunner,          // inject fuzz runner
			dict.NewDictGrabber,         // inject dict grabber
			crash.NewCrashManager,       // inject crash manager
			seeds.NewSeedManager,        // inject seed manager
			watchdog.NewWatchDogFactory, // inject watchdog factory
		),
		aflpp.AFLModule,             // inject AFL++ fuzzer module
		corpus.CorpusGrabbersModule, // inject seed grabbers
		fx.Invoke(
			setUpMmapRNDBits, // set up mmap_rnd_bits
			scheduler.NewScheduler,
		),
		fx.WithLogger(func(log *zap.Logger) fxevent.Logger {
			zlogger := fxevent.ZapLogger{Logger: log}
			zlogger.UseLogLevel(zap.DebugLevel)
			return &zlogger
		}),
	)
	app.Run()
}

package database

import (
	"crs-scheduler/config"

	"go.uber.org/zap"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func NewDBConnection(appConfig *config.AppConfig, logger *zap.Logger) *gorm.DB {
	connectionString := appConfig.DatabaseURL
	db, err := gorm.Open(postgres.Open(connectionString), &gorm.Config{})
	if err != nil {
		logger.Fatal("failed to connect database", zap.Error(err))
	}
	logger.Info("connected to database")
	return db
}

package repository

import (
	"crs-scheduler/models"

	"gorm.io/gorm"
)

type SarifRepository interface {
	GetNewSarif() ([]models.Sarif, error)
}

type SarifRepositoryImpl struct {
	db *gorm.DB
}

func NewSarifRepository(db *gorm.DB) SarifRepository {
	return &SarifRepositoryImpl{db: db}
}

func (r *SarifRepositoryImpl) GetNewSarif() ([]models.Sarif, error) {
	var sarifs []models.Sarif
	result := r.db.Joins("JOIN tasks ON sarifs.task_id = tasks.id").
		Where("tasks.status = ?", "processing").
		Find(&sarifs)
	if result.Error != nil {
		return nil, result.Error
	}
	return sarifs, nil
}

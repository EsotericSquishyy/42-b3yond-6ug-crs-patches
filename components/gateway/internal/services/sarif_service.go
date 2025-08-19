package services

import (
	"crs-gateway/gen/models"
	"crs-gateway/internal/db"
	"encoding/json"
	"fmt"

	"gorm.io/datatypes"
	"gorm.io/gorm"
)

type SarifService interface {
	CreateSarif(sarif *models.TypesSARIFBroadcast, messageID string) error
}

type SarifServiceImpl struct {
	db *gorm.DB
}

func NewSarifService(db *gorm.DB) SarifService {
	return &SarifServiceImpl{
		db: db,
	}
}

func (s *SarifServiceImpl) CreateSarif(sarif *models.TypesSARIFBroadcast, messageID string) error {
	for _, broadcast := range sarif.Broadcasts {
		if err := s.createSingleBroadcast(broadcast, messageID); err != nil {
			return fmt.Errorf("failed to create broadcast: %w", err)
		}
	}

	return nil
}

func (s *SarifServiceImpl) createSingleBroadcast(broadcast *models.TypesSARIFBroadcastDetail, messageID string) error {
	sarifJSON, err := json.Marshal(broadcast.Sarif)
	if err != nil {
		return fmt.Errorf("failed to marshal sarif: %w", err)
	}

	metadataJSON, err := json.Marshal(broadcast.Metadata)
	if err != nil {
		return fmt.Errorf("failed to marshal metadata: %w", err)
	}

	sarif := &db.Sarif{
		ID:        broadcast.SarifID.String(),
		TaskID:    broadcast.TaskID.String(),
		MessageID: messageID,
		Sarif:     datatypes.JSON(sarifJSON),
		Metadata:  datatypes.JSON(metadataJSON),
	}

	if err := s.db.Create(sarif).Error; err != nil {
		return fmt.Errorf("failed to create sarif: %w", err)
	}

	return nil
}

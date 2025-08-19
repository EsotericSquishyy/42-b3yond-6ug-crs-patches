package api

import (
	"crs-scheduler/config"
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"go.uber.org/zap"
)

type QueueService struct {
	managementEndpoint string
	logger             *zap.Logger
}

func NewQueueService(config *config.AppConfig, logger *zap.Logger) *QueueService {
	return &QueueService{managementEndpoint: config.RabbitMQManagementEndpoint, logger: logger}
}

func (q *QueueService) GetQueueLength(queueName string) (int64, error) {
	url := fmt.Sprintf("%s/api/queues/%%2F/%s", q.managementEndpoint, queueName)

	resp, err := http.Get(url)
	if err != nil {
		q.logger.Error("failed to get queue length", zap.Error(err))
		return 0, fmt.Errorf("failed to get queue length: %w", err)
	}

	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		q.logger.Error("failed to read response body", zap.Error(err))
		return 0, fmt.Errorf("failed to read response body: %w", err)
	}

	var queueInfo struct {
		Messages        int64 `json:"messages"`
		MessagesUnacked int64 `json:"messages_unacknowledged"`
		MessagesReady   int64 `json:"messages_ready"`
	}

	err = json.Unmarshal(body, &queueInfo)
	if err != nil {
		q.logger.Error("failed to unmarshal response body", zap.Error(err))
		return 0, fmt.Errorf("failed to unmarshal response body: %w", err)
	}

	q.logger.Info("queue info", zap.String("queueName", queueName), zap.Int64("messages", queueInfo.Messages), zap.Int64("messagesUnacked", queueInfo.MessagesUnacked), zap.Int64("messagesReady", queueInfo.MessagesReady))

	return queueInfo.MessagesUnacked + queueInfo.MessagesReady, nil
}

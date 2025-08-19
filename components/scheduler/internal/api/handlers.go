package api

import (
	"encoding/json"
	"net/http"

	"go.uber.org/zap"
)

// StatusResponse represents the response from the status endpoint
type StatusResponse struct {
	TaskCount int64 `json:"task_count"`
}

// QueueResponse represents the response from the queue endpoint
type QueueResponse struct {
	QueueName string `json:"queue_name"`
	Length    int64  `json:"length"`
}

// handleHealth returns the health status of the application
func handleHealth(healthService *HealthService, logger *zap.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ready := healthService.IsReady()
		logger.Info("received health check request", zap.Bool("ready", ready))
		if !ready {
			http.Error(w, "Not ready", http.StatusServiceUnavailable)
			return
		}

		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ready"))
	}
}

// handleStatus returns the current number of processing and waiting tasks
func handleStatus(statusService *StatusService, logger *zap.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		count, err := statusService.GetTaskCount()
		if err != nil {
			logger.Error("received status request, but failed to get task count", zap.Error(err))
			http.Error(w, "Failed to get task count", http.StatusInternalServerError)
			return
		}
		logger.Info("received status request", zap.Int64("task_count", count))

		response := StatusResponse{
			TaskCount: count,
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(response)
	}
}

// handleQueue returns the current length of the specified queue (NACKed + pending)
func handleQueue(queueService *QueueService, logger *zap.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		queueName := r.URL.Query().Get("queue")
		if queueName == "" {
			http.Error(w, "Queue name is required", http.StatusBadRequest)
			return
		}

		logger.Info("received queue length request", zap.String("queueName", queueName))

		length, err := queueService.GetQueueLength(queueName)
		if err != nil {
			logger.Error("received queue length request, but failed to get queue length", zap.Error(err))
			http.Error(w, "Failed to get queue length", http.StatusInternalServerError)
			return
		}

		response := QueueResponse{
			QueueName: queueName,
			Length:    length,
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(response)
	}
}

func handleHarness(harnessService *HarnessService, logger *zap.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		logger.Info("received harness request")

		response, err := harnessService.GetHarnessData()
		if err != nil {
			logger.Error("received harness request, but failed to get harness data", zap.Error(err))
			http.Error(w, "Failed to get harness data", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(response)
	}
}

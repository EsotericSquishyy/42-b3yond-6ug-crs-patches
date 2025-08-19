package messaging

import (
	"go.uber.org/zap"
)

const (
	// Fanout exchanges
	TaskBroadcastExchange   = "task_broadcast_exchange"   // fanout exchange for broadcasting tasks
	CancelBroadcastExchange = "cancel_broadcast_exchange" // fanout exchange for broadcasting cancel signals

	// Direct exchange
	DirectExchange = "direct_exchange" // direct exchange for routing tasks and other messages

	// Queues
	PrimeFuzzingQueue    = "prime_fuzzing_queue"
	GeneralFuzzingQueue  = "general_fuzzing_queue"
	DirectedFuzzingQueue = "directed_fuzzing_queue"
	SeedgenQueue         = "seedgen_queue"
	CorpusQueue          = "corpus_queue"
	FuncTestQueue        = "func_test_queue"
	SarifQueue           = "sarif_queue"
	TriageQueue          = "triage_queue"
	PatchQueue           = "patch_queue"
	ArtifactQueue        = "artifact_queue"
)

var (
	allQueues = []string{
		PrimeFuzzingQueue,
		GeneralFuzzingQueue,
		DirectedFuzzingQueue,
		SeedgenQueue,
		CorpusQueue,
		FuncTestQueue,
		SarifQueue,
		TriageQueue,
		PatchQueue,
		ArtifactQueue,
	}
	taskBroadcastGroup = []string{
		PrimeFuzzingQueue,
		GeneralFuzzingQueue,
		DirectedFuzzingQueue,
		SeedgenQueue,
		CorpusQueue,
		FuncTestQueue,
		ArtifactQueue,
	}
	priorityEnabled = map[string]bool{
		PatchQueue:  true,
		TriageQueue: true,
	}
)

type MQInitializer struct {
	rabbitMQ RabbitMQ
	logger   *zap.Logger
}

// initializeRabbitMQ declares the exchanges, queues, and bindings needed.
func InitializeMQ(rabbitMQ RabbitMQ, logger *zap.Logger) error {
	m := &MQInitializer{
		rabbitMQ: rabbitMQ,
		logger:   logger,
	}

	// declare direct exchange
	if err := m.declareExchange(DirectExchange, "direct"); err != nil {
		m.logger.Error("failed to declare direct exchange", zap.Error(err))
		return err
	}

	// Declare fanout exchanges.
	if err := m.declareExchange(TaskBroadcastExchange, "fanout"); err != nil {
		m.logger.Error("failed to declare task broadcast exchange", zap.Error(err))
		return err
	}
	if err := m.declareExchange(CancelBroadcastExchange, "fanout"); err != nil {
		m.logger.Error("failed to declare cancel broadcast exchange", zap.Error(err))
		return err
	}

	// Declare all queues.
	for _, queueName := range allQueues {
		if err := m.declareQueue(queueName); err != nil {
			m.logger.Error("failed to declare queue", zap.String("queue", queueName), zap.Error(err))
			return err
		}
	}

	// bind each task queue.
	for _, queueName := range taskBroadcastGroup {
		// Bind to the task_broadcast exchange (fanout binding—routing key is ignored).
		if err := m.bindQueue(queueName, "", TaskBroadcastExchange); err != nil {
			m.logger.Error("failed to bind queue to task broadcast exchange", zap.String("queue", queueName), zap.Error(err))
			return err
		}
	}

	m.logger.Info("successfully initialized RabbitMQ exchanges, queues, and bindings")
	return nil
}

// declareExchange declares an exchange of the given kind.
func (s *MQInitializer) declareExchange(name, kind string) error {
	channel := s.rabbitMQ.GetChannel()
	defer channel.Close()

	return channel.ExchangeDeclare(
		name,
		kind,
		true,  // durable
		false, // auto-deleted
		false, // internal
		false, // no-wait
		nil,   // arguments
	)
}

// declareQueue declares a durable queue and then bind it to the direct exchange.
func (s *MQInitializer) declareQueue(name string) error {
	channel := s.rabbitMQ.GetChannel()
	defer channel.Close()

	args := make(map[string]any)
	if priorityEnabled[name] {
		args["x-max-priority"] = 10
	}

	_, err := channel.QueueDeclare(
		name,
		true,  // durable
		false, // auto-deleted
		false, // exclusive
		false, // no-wait
		args,  // arguments
	)
	if err != nil {
		return err
	}

	return s.bindQueue(name, name, DirectExchange)
}

// bindQueue creates a binding between a queue and an exchange with the specified routing key.
func (s *MQInitializer) bindQueue(queueName, routingKey, exchange string) error {
	channel := s.rabbitMQ.GetChannel()
	defer channel.Close()

	return channel.QueueBind(
		queueName,
		routingKey,
		exchange,
		false, // no-wait
		nil,   // arguments
	)
}

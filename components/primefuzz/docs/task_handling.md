# Task Queue Priority Handling

This document describes how tasks are handled from a priority message queue in the prime fuzzing workflow.

## An example of task cancel message

* `task_id` contains a UUID like "2b8cb6fc-f3a8-4d15-aaf3-403238a456ea"
* `task_type` is set to "cancel", indicating this is a cancellation task

```
{"task_id":"2b8cb6fc-f3a8-4d15-aaf3-403238a456ea","task_type":"cancel"}
```

## Priority Queue Setup

The message queue is configured with priority support (0-10) when declared:

```python
queue = await channel.declare_queue(
    queue_name, 
    durable=True,
    arguments={"x-max-priority": 10}
)
```

## Task Priority Management 

The workflow handles task priorities in several ways:

1. Initial message publishing with default priority:
```python 
channel.basic_publish(
    exchange="",
    routing_key="general_fuzzing_queue", 
    body=message_json,
    properties=pika.BasicProperties(
        priority=0,  # Default priority
        delivery_mode=2  # Persistent messages
    )
)
```

2. Priority escalation for requeued tasks:
```python
# From workflow.py
if self.task_priority_map.get(message_id, 5) >= 5:
    prio = prio + 1 if prio < 10 else 10 
    self.task_priority_map[message_id] = prio
```

## Message Processing Flow

1. Message consumer processes one message at a time with QoS:
```python
await channel.set_qos(prefetch_count=1)
```

2. Messages are requeued when:
- Maximum workers are reached
- Task directory already exists  
- Message was already processed
- Task cancellation fails

3. Requeued messages get higher priority:
```python
new_message = aio_pika.Message(
    body=message.body,
    message_id=message.message_id, 
    headers=message.headers,
    priority=prio  # Increased priority
)
```

This ensures critical tasks eventually get processed while maintaining system stability.

**Combined together**

```python
    async with message.process(ignore_processed=True):
        logger.debug("Processing new tasks")
        task = message.body
        payload = json.loads(task.decode("unicode_escape"))
        task_id = payload.get("task_id")
        task_type = payload.get("task_type", "")
        no_cancel_error = True
        # should skip
        if task_type.strip() == "cancel" and task_id:
            # Note: I will merge the predicates later
            no_cancel_error = await self.setup_stop_signal(task_id)
            if no_cancel_error:
                return

        # requeue on cancel error or no enough workers
        if (not no_cancel_error) or await self.should_skip_task(task_id):
            await self.requeue_message_to_end(message)
            return

        await self.process_task(payload)
        await self.mark_message_processed(message_id)
```

**Example: Deferred acknowledgment for long-running tasks**

```python
async with ProcessingContext(message) as ctx:
    result = await long_running_task()
    if result.success:
        await ctx.message.ack()
    else:
        await ctx.message.nack(requeue=True)
```

## Important Considerations

* Always ack/nack messages to prevent queue buildup
* Use requeue=False when permanently rejecting messages
* Consider implementing a dead letter exchange for failed messages
* Monitor unacknowledged message count in queue metrics
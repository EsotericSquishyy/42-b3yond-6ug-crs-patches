from mq import MsgQueue
import os
import asyncio
import json

async def test_msg_queue():
    # Initialize the message queue
    queue_name = "test_queue"
    rabbitmq_url = "amqp://guest:guest@localhost:5672/"
    
    os.environ['CMIN_QUEUE'] = queue_name
    os.environ['RABBITMQ_URL'] = rabbitmq_url
    os.environ['REDIS_RO_URL'] = "redis://localhost:6379"
    os.environ['REDIS_RW_URL'] = "redis://localhost:6379"
    
    # Create a new MsgQueue instance
    msg_queue = MsgQueue(rabbitmq_url, queue_name, None, debug=True)
    
    await msg_queue.connect()
    
    # Send a test message
    test_message = {
        "task_id": "11111111-1111-1111-1111-111111111111",
        "harness": "schema",
        "seeds": "/home/acd/cminplusplus/tests/seeds.tar.gz"
    }
    await msg_queue.send(json.dumps(test_message))
    
if __name__ == "__main__":
    asyncio.run(test_msg_queue())
    
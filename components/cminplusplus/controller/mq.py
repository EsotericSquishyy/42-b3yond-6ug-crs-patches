import aio_pika
import asyncio
import logging

class MsgQueue:
    def __init__(self, url, queue, loop, debug = False):
        if debug:
            logging.debug('Connecting to RabbitMQ at %s', url)
        self.queue_name = queue
        # self.exchange = exchange
        # self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=host, port=port, credentials=pika.PlainCredentials(os.getenv('RABBITMQ_USER'), os.getenv('RABBITMQ_PASS'))))
        # connect using a connection string
        self.url = url
        self.loop = loop
        # self.init_impl(url, queue, loop)
        self.connection = None
        # asyncio.run(self.connect())
            
    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=28)
        self.queue = await self.channel.declare_queue(self.queue_name, durable=True)
            

    async def send(self, msg):
        if self.channel is None:
            await self.connect()
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=msg.encode()),
            routing_key=self.queue_name,
        )

    async def close(self):
        await self.connection.close()

    async def consume(self, callback, wait=True):
        if self.queue is None:
            await self.connect()
        await self.queue.consume(callback)
        if wait:
            await asyncio.Future()
        
    
                    
    

        
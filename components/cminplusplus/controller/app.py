import os
import logging
import asyncio
import sys

from logs import init_logging
from mq import MsgQueue

from mock import test_msg_queue

from tasks import on_message_wrapper
from rio import RedisStore

async def main(loop):
    logging.getLogger('aio_pika').setLevel(logging.WARNING)
    init_logging(debug=False)
    logging.info('''   
                               
 ██████╗██████╗ ███████╗     ██████╗██╗     ██╗   ██╗███████╗████████╗███████╗██████╗      ██████╗███╗   ███╗██╗███╗   ██╗
██╔════╝██╔══██╗██╔════╝    ██╔════╝██║     ██║   ██║██╔════╝╚══██╔══╝██╔════╝██╔══██╗    ██╔════╝████╗ ████║██║████╗  ██║
██║     ██████╔╝███████╗    ██║     ██║     ██║   ██║███████╗   ██║   █████╗  ██████╔╝    ██║     ██╔████╔██║██║██╔██╗ ██║
██║     ██╔══██╗╚════██║    ██║     ██║     ██║   ██║╚════██║   ██║   ██╔══╝  ██╔══██╗    ██║     ██║╚██╔╝██║██║██║╚██╗██║
╚██████╗██║  ██║███████║    ╚██████╗███████╗╚██████╔╝███████║   ██║   ███████╗██║  ██║    ╚██████╗██║ ╚═╝ ██║██║██║ ╚████║
 ╚═════╝╚═╝  ╚═╝╚══════╝     ╚═════╝╚══════╝ ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝     ╚═════╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝                                                                                                                          
''')
    
    logging.info('Turning off ASLR')
    ret = os.system('echo 0 | tee /proc/sys/kernel/randomize_va_space')
    if ret != 0:
        logging.error('Failed to turn off ASLR')
        exit(1)
    
    
    logging.info('Starting message queue')

    
    if len(sys.argv) > 1 and sys.argv[1] == '--mock':
        logging.warning('Running in mock mode')
        await test_msg_queue()
        # exit(0)
        
    
    
    queue_name = os.getenv('CMIN_QUEUE')
    rabbitmq_url = os.getenv('RABBITMQ_URL')
    # redis_ro_url = os.getenv('REDIS_RO_URL')
    # redis_rw_url = os.getenv('REDIS_RW_URL')
    redis_sentinel = os.getenv('REDIS_SENTINEL_HOSTS')
    redis_master = os.getenv('REDIS_MASTER_NAME')
    seed_storage_prefix = os.getenv('SEED_STORAGE_PREFIX')
    
    if not queue_name or not rabbitmq_url or not redis_sentinel or not redis_master or not seed_storage_prefix:
        logging.error('Missing environment variables. Check CMIN_QUEUE, RABBITMQ_URL, REDIS_SENTINEL_HOSTS, REDIS_MASTER_NAME, SEED_STORAGE_PREFIX')
        exit(1)
    
    
    
    try:
        msg_queue = MsgQueue(rabbitmq_url, queue_name, loop, debug=True)
        await msg_queue.connect()
    except Exception as e:
        logging.error('Failed to connect to RabbitMQ: %s', e)
        exit(1)
        
    logging.info('Connected to RabbitMQ')

    try:
        ro_redis = RedisStore(redis_sentinel, sentinel=True, mastername=redis_master, slave=True)
        rw_redis = RedisStore(redis_sentinel, sentinel=True, mastername=redis_master, slave=False)
        await ro_redis.redis.ping()
        await rw_redis.redis.ping()
        logging.info('Connected to Redis')
    except Exception as e:
        logging.error('Failed to connect to Redis: %s', e)
        exit(1)

    try:
        logging.info('Starting message queue consumer')
        await msg_queue.consume(on_message_wrapper(ro_redis, rw_redis, seed_storage_prefix, msg_queue), wait = False)
    except KeyboardInterrupt:
        logging.info('Stopping message queue consumer')
        
    await asyncio.sleep(10000000)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(main(loop))
    
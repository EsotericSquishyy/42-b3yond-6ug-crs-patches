import logging
import os
import asyncio 
from workers import db_worker, submit_worker, confirm_worker, bundle_worker
from redisio import MessageSet, RedisStore
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

async def main():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logging.error("Database URL is not set")
        exit(1)
    base_url = os.getenv('COMPETITION_URL', 'http://localhost:8080/')
    # redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    redis_sentinel_hosts = os.getenv('REDIS_SENTINEL_HOSTS', 'localhost:26379')
    redis_master = os.getenv('REDIS_MASTER', 'mymaster')
    api_user = os.getenv('API_USER', "foo")
    api_pass = os.getenv('API_PASS', "bar")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318"),
    data_refresh_interval = int(os.getenv('DATA_REFRESH_INTERVAL', 300))
    if not api_user or not api_pass:
        logging.error("API_USER or API_PASS is not set")
        exit(1)
    logging.info(f"Database URL: {db_url}")
    logging.info(f"Competition URL: {base_url}")
    # logging.info(f"Redis URL: {redis_url}")
    logging.info(f"Redis Sentinel Hosts: {redis_sentinel_hosts}")
    logging.info(f"Redis Master: {redis_master}")
    logging.info(f"Data refresh interval: {data_refresh_interval}")
    logging.info(f"OTLP Endpoint: {otlp_endpoint}")
    # task_queue = MessageQueue(redis_url, "task_queue")
    # confirm_queue = MessageQueue(redis_url, "confirm_queue")
    task_set = MessageSet(redis_sentinel_hosts, "task_set", sentinel=True, mastername=redis_master)
    confirm_set = MessageSet(redis_sentinel_hosts, "confirm_set", sentinel=True, mastername=redis_master)
    bundle_set = MessageSet(redis_sentinel_hosts, "bundle_set", sentinel=True, mastername=redis_master)
    storage = RedisStore(redis_sentinel_hosts, sentinel=True, mastername=redis_master)
    try:
        await task_set.redis.ping()
        await confirm_set.redis.ping()
        await bundle_set.redis.ping()
        await storage.redis.ping()
    except Exception as e:
        logging.error(f"Failed to connect to Redis: {e}")
        exit(1)
        
    db_engine = create_engine(db_url,
        pool_pre_ping = True,
        pool_recycle = data_refresh_interval,
        max_overflow = 0,
        pool_size = 20,
        pool_timeout = 30,
    )

    db_task = asyncio.create_task(db_worker(db_engine, task_set, storage, data_refresh_interval))
    submit_task = asyncio.create_task(submit_worker(base_url, task_set, confirm_set, storage))
    confirm_task = asyncio.create_task(confirm_worker(base_url, confirm_set, db_engine, bundle_set, storage, task_set))
    bundle_task = asyncio.create_task(bundle_worker(base_url, bundle_set, storage))    
    await asyncio.gather(db_task, submit_task, confirm_task)
    
    
if __name__ == "__main__":
    if os.getenv("AIXCC_DEBUG"):
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

    # bug, patch, sarif report, bundle
    # redis <submitter:xxy:yyx>
    
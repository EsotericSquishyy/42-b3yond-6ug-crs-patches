import redis.asyncio as aioredis
import logging
import asyncio

# a decorator to handle redis connection errors
def redis_connection_error_handler(func):
    async def wrapper(*args, **kwargs):
        for attempt in range(3):
            try:
                return await func(*args, **kwargs)
            except aioredis.ConnectionError as e:
                logging.error(f"Redis connection error: {e}")
                if attempt < 2:
                    if hasattr(args[0], 'sentinel') and args[0].sentinel:
                        args[0].redis = args[0].sentinel.master_for(args[0].mastername, socket_timeout=30.0, retry_on_timeout=True, retry_on_error=[aioredis.ConnectionError])
                    else:
                        raise
                    await asyncio.sleep(3)
                else:
                    raise
            except aioredis.TimeoutError as e:
                logging.error(f"Redis timeout error: {e}")
                if attempt < 2:
                    if hasattr(args[0], 'sentinel') and args[0].sentinel:
                        args[0].redis = args[0].sentinel.master_for(args[0].mastername, socket_timeout=30.0, retry_on_timeout=True, retry_on_error=[aioredis.ConnectionError])
                    else:
                        raise
                    await asyncio.sleep(3)
                else:
                    raise
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                raise
    return wrapper

class MessageQueue:
    def __init__(self, url, queue_name, sentinel=False, mastername="mymaster"):
        if sentinel:
            self.mastername = mastername
            self.sentinel_hosts = [(h, int(p)) for h, p in (item.split(":") for item in url.split(","))]
            self.sentinel = aioredis.Sentinel(self.sentinel_hosts, socket_timeout=30.0)
            self.redis = self.sentinel.master_for(mastername, socket_timeout=30.0, retry_on_timeout=True, retry_on_error=[aioredis.ConnectionError])
        else:
            pool = aioredis.ConnectionPool.from_url(url)
            self.redis = aioredis.Redis.from_pool(pool)
            self.sentinel = None
        self.queue_name = queue_name

    @redis_connection_error_handler
    async def push(self, message):
        await self.redis.lpush(self.queue_name, message)

    @redis_connection_error_handler
    async def pop(self):
        return await self.redis.rpop(self.queue_name)

    @redis_connection_error_handler
    async def is_empty(self):
        return await self.redis.llen(self.queue_name) == 0
    
class MessageSet:
    def __init__(self, url, set_name, sentinel=False, mastername="mymaster"):
        if sentinel:
            self.mastername = mastername
            sentinel_hosts = [(h, int(p)) for h, p in (item.split(":") for item in url.split(","))]
            self.sentinel = aioredis.Sentinel(sentinel_hosts, socket_timeout=30.0)
            self.redis = self.sentinel.master_for(mastername, socket_timeout=30.0, retry_on_timeout=True, retry_on_error=[aioredis.ConnectionError])
        else:
            pool = aioredis.ConnectionPool.from_url(url)
            self.redis = aioredis.Redis.from_pool(pool)
            self.sentinel = None
        self.set_name = set_name
    
    @redis_connection_error_handler
    async def add(self, message):
        await self.redis.sadd(self.set_name, message)
    
    @redis_connection_error_handler
    async def remove(self, message):
        await self.redis.srem(self.set_name, message)
    
    @redis_connection_error_handler
    async def get_one(self):
        return await self.redis.srandmember(self.set_name)
        
    
class RedisStore:
    def __init__(self, url, sentinel=False, mastername="mymaster"):
        if sentinel:
            self.mastername = mastername
            self.sentinel_hosts = [(h, int(p)) for h, p in (item.split(":") for item in url.split(","))]
            self.sentinel = aioredis.Sentinel(self.sentinel_hosts, socket_timeout=30.0)
            self.redis = self.sentinel.master_for(mastername, socket_timeout=30.0, retry_on_timeout=True, retry_on_error=[aioredis.ConnectionError])
        else:
            pool = aioredis.ConnectionPool.from_url(url)
            self.redis = aioredis.Redis.from_pool(pool)
            self.sentinel = None

    @redis_connection_error_handler
    async def set(self, key, value):
        await self.redis.set(key, value)

    @redis_connection_error_handler
    async def get(self, key):
        return await self.redis.get(key)

    @redis_connection_error_handler
    async def delete(self, key):
        await self.redis.delete(key)
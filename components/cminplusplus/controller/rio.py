import redis.asyncio as aioredis        
    
class RedisStore:
    def __init__(self, url, sentinel=False, mastername="mymaster", slave = False):
        if sentinel:
            sentinel_hosts = [(h, int(p)) for h, p in (item.split(":") for item in url.split(","))]
            sentinel = aioredis.Sentinel(sentinel_hosts, socket_timeout=20.0)
            if slave:
                self.redis = sentinel.slave_for(mastername, socket_timeout=20.0, retry_on_timeout=True, retry_on_error=[aioredis.ConnectionError])
            else:
                self.redis = sentinel.master_for(mastername, socket_timeout=20.0, retry_on_timeout=True, retry_on_error=[aioredis.ConnectionError])
        else:
            pool = aioredis.ConnectionPool.from_url(url)
            self.redis = aioredis.Redis.from_pool(pool)

    async def set(self, key, value):
        await self.redis.set(key, value)

    async def get(self, key):
        return await self.redis.get(key)

    async def delete(self, key):
        await self.redis.delete(key)

    async def set_add(self, key, value):
        await self.redis.sadd(key, *value)

    async def set_remove(self, key, *value):
        await self.redis.srem(key, value)

    async def set_get(self, key):
        return await self.redis.smembers(key)
    
    async def set_member_exists(self, key, value):
        return await self.redis.sismember(key, value)
    
    def pipeline(self):
        return self.redis.pipeline()
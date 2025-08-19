from redis import Redis
from redis.sentinel import Sentinel
from redis.connection import ConnectionPool

class RedisStorage:
    def __init__(self, url, sentinel=False, mastername="mymaster"):
        if sentinel:
            sentinel_hosts = [(h, int(p)) for h, p in (item.split(":") for item in url.split(","))]
            self.sentinel = Sentinel(sentinel_hosts, socket_timeout=5.0)
            try:
                self.redis = self.sentinel.master_for(mastername, socket_timeout=5.0)
                self.redis.ping()
            except Exception as e:
                print(f"Error connecting to Redis Sentinel: {e}")
                raise e
        else:
            connection_pool = ConnectionPool.from_url(url, socket_timeout=5.0)
            self.redis = Redis(connection_pool=connection_pool)
            try: 
                self.redis.ping()
            except Exception as e:
                print(f"Error connecting to Redis: {e}")
                raise e

    def set(self, key, value):
        self.redis.set(key, value)

    def get(self, key):
        return self.redis.get(key)

    def delete(self, key):
        self.redis.delete(key)
    
    
import redis
from redis.sentinel import Sentinel
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.exceptions import (
    BusyLoadingError,
    ConnectionError,
    TimeoutError
)

redis_client = None
sentinel = None
sentinel_hosts = None
master_name = None
redis_password = None
redis_db = 0


def init_redis(sentinel_hosts_list, master_name_str, password=None, db=0):
    """
    Initialize Redis client using Sentinel

    Args:
        sentinel_hosts_list (list): List of (host, port) tuples for Sentinel nodes
        master_name_str (str): Name of the master to monitor
        password (str, optional): Redis password
        db (int, optional): Redis database number
    """
    global redis_client, sentinel, sentinel_hosts, master_name, redis_password, redis_db

    # Store configuration for reconnection if needed
    sentinel_hosts = sentinel_hosts_list
    master_name = master_name_str
    redis_password = password
    redis_db = db

    # Initialize Sentinel
    sentinel = Sentinel(sentinel_hosts, socket_timeout=30.0, password=password)

    try:
        # Get master for the specified master name with failover support
        retry = Retry(ExponentialBackoff(), 3)
        redis_client = sentinel.master_for(
            master_name,
            socket_timeout=30.0,
            password=password,
            db=db,
            retry=retry,
            retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError]
        )

        if redis_client.ping():
            print(
                f"Redis client initialized via Sentinel for master '{master_name}'")
    except redis.exceptions.ConnectionError as e:
        print(f"Redis Sentinel connection failed: {e}")
        raise


def get_redis_client():
    global redis_client, sentinel

    # Try to ping the current client
    try:
        if redis_client and redis_client.ping():
            return redis_client
    except (ConnectionError, TimeoutError, BusyLoadingError):
        # Connection failed, try to reconnect
        try:
            retry = Retry(ExponentialBackoff(), 3)
            redis_client = sentinel.master_for(
                master_name,
                socket_timeout=30.0,
                password=redis_password,
                db=redis_db,
                retry=retry,
                retry_on_error=[BusyLoadingError,
                                ConnectionError, TimeoutError]
            )
            if redis_client.ping():
                print("Redis client reconnected successfully")
                return redis_client
        except Exception as e:
            print(f"Redis reconnection failed: {e}")
            raise

    return redis_client


def get_sentinel():
    """Get the Sentinel object for additional operations if needed"""
    return sentinel

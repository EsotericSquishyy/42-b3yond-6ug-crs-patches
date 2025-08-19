from aiohttp import web
import os
from rio import RedisStore
from cmin import handle_cmin
import asyncio
from logs import init_logging
import logging

async def ping(request):
    return web.Response(text="This is Nightu Fan Club")

async def handle(request):
    task = request.match_info.get('task', None)
    harness = request.match_info.get('harness', None)
    if task is None or harness is None:
        return web.Response(text="Invalid request", status=400)
    path = await handle_cmin(task, harness, request.app['redis_ro'], request.app['redis_rw'], request.app['shared_storage_prefix'], request.app['seed_storage_prefix'], request.app['cache_timeout'])
    if path is None:
        return web.Response(text="Not Found", status=404)
    if path is False:
        return web.Response(text="Internal Server Error", status=500)
    return web.Response(text=path)


async def init_webserver(app):
    # redis_ro_url = os.getenv('REDIS_RO_URL')
    # redis_rw_url = os.getenv('REDIS_RW_URL')
    init_logging(debug=False)
    redis_sentinel = os.getenv('REDIS_SENTINEL_HOSTS')
    redis_master = os.getenv('REDIS_MASTER_NAME')
    shared_storage_prefix = os.getenv('SHARED_STORAGE_PREFIX')
    seed_storage_prefix = os.getenv('SEED_STORAGE_PREFIX')
    cache_timeout = os.getenv('CACHE_TIMEOUT')
    if not redis_sentinel or not redis_master or not shared_storage_prefix or not seed_storage_prefix:
        logging.error('Missing environment variables. Check REDIS_SENTINEL_HOSTS, REDIS_MASTER_NAME, SHARED_STORAGE_PREFIX, SEED_STORAGE_PREFIX, CACHE_TIMEOUT')
        raise Exception('Missing environment variables')
    app['cache_timeout'] = cache_timeout
    try:
        app['redis_ro'] = RedisStore(redis_sentinel, sentinel=True, mastername=redis_master, slave=True)
        app['redis_rw'] = RedisStore(redis_sentinel, sentinel=True, mastername=redis_master, slave=False)
        await app['redis_ro'].redis.ping()
        await app['redis_rw'].redis.ping()
        logging.info('Connected to Redis')
    except Exception as e:
        logging.error('Failed to connect to Redis: %s' % e)
        raise Exception('Failed to connect to Redis')
    try:
        os.stat(shared_storage_prefix)
        app['shared_storage_prefix'] = os.path.join(shared_storage_prefix, 'cmin-calculator')
        if not os.path.exists("/seedcache"):
            os.makedirs("/seedcache", exist_ok=True)
            logging.info('Created seed cache directory: /seedcache')
        else:
            logging.info('Seed cache directory exists: /seedcache')
        if not os.path.exists(app['shared_storage_prefix']):
            os.makedirs(app['shared_storage_prefix'], exist_ok=True)
            logging.info('Created shared storage prefix: %s' % app['shared_storage_prefix'])
        else:
            logging.info('Shared storage prefix exists: %s' % app['shared_storage_prefix'])
        # logging.info('Shared storage prefix exists: %s' % shared_storage_prefix)
    except Exception as e:
        logging.error('Failed to set shared storage prefix: %s' % e)
        raise Exception('Failed to set shared storage prefix')
    try:
        app['seed_storage_prefix'] = seed_storage_prefix
        os.stat(seed_storage_prefix)
        logging.info('Seed storage prefix exists: %s' % seed_storage_prefix)
    except Exception as e:
        logging.error('Failed to set seed storage prefix: %s' % e)
        raise Exception('Failed to set seed storage prefix')
    

app = web.Application()
app.add_routes([web.get('/', ping),
                web.get('/cmin/{task}/{harness}', handle)])
app.on_startup.append(init_webserver)

if __name__ == '__main__':
    web.run_app(app, port=80)
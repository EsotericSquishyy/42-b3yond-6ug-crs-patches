import time
import tarfile
import os
import asyncio
import logging
import uuid
import shutil
# import json
local_cache = {}
futures = {}
lock = asyncio.Lock()

async def handle_cmin(task, harness, redis_ro, redis_rw, shared_storage_prefix = None, seed_storage_prefix = None, cache_timeout = 600):
    try:
        cache_timeout = int(cache_timeout)
        if cache_timeout < 0:
            cache_timeout = 0
        current_time = int(time.time())
        # L1 cache: check if the result is already in local cache
        if f'{task}:{harness}' in local_cache and current_time - local_cache[f'{task}:{harness}'][1] < cache_timeout:
            logging.info(f'Local cache hit: {task}:{harness}, returning')
            return local_cache[f'{task}:{harness}'][0]
        # L2 cache: check if the result is already in Redis
        file_cache_key = f'clustercmin:file:{task}:{harness}'
        result = await redis_ro.get(file_cache_key)
        if result:
            # <filename>:<timestamp>
            result = result.decode('utf-8')
            filename, timestamp = result.split(':')
            if current_time - int(timestamp) < cache_timeout:
                # Update local cache
                local_cache[f'{task}:{harness}'] = (filename, int(timestamp))
                logging.info(f'Redis cache hit: {task}:{harness}, returning')
                return filename
        
        # No cache hit, proceed with the computation
        key = f'clustercmin:features:{task}:{harness}'
        features = await redis_ro.set_get(key)
        if not features:
            logging.warning(f'No features found for task {task} and harness {harness}, maybe not finished yet')
            return None
        
        # when the code comes here, it means:
        # 1. the cache is empty - no cache, no future
        # 2. the cache has expired - with cache, future has a result
        future_key = f'clustercmin:future:{task}:{harness}'
        event_loop = asyncio.get_event_loop()
        
        async def create_and_save_tarfile():
        
            feature_list = [f.decode('utf-8') for f in features]
            logging.info(f'Got {len(feature_list)} features for task {task} and harness {harness}')

            # create directory
            # dir_name = os.path.join(shared_storage_prefix, 'minimized', task, harness)
            # os.makedirs(dir_name, exist_ok=True)
            

            # cleanup old files - do we need this?
            # if os.path.exists(dir_name):
            #     for f in os.listdir(dir_name):
            #         os.remove(os.path.join(dir_name, f))

            # original seeds directory, NEED TO CHECK
            # original_seeds_dir = os.path.join(shared_storage_prefix, 'original', task, harness)
            # if not os.path.exists(original_seeds_dir):
            #     print(f'Original seeds directory {original_seeds_dir} does not exist, returning')
            #     return None

            # get file list from redis
            logging.info(f'Getting file list for task {task} and harness {harness}')
            tarfile_list = []
            pipeline = redis_ro.pipeline()
            for feature in feature_list:
                # get filename from redis
                pipeline.get(f'clustercmin:file:{task}:{harness}:{feature}')
                # filename = await redis_ro.get(f'clustercmin:file:{task}:{harness}:{feature}')
            filenames = await pipeline.execute()
            download_count = 0
            for filename in filenames:
                if filename:
                    # print(f'Got filename {filename} for task {task} and harness {harness}')
                    filename = filename.decode('utf-8')
                    cached_filename = os.path.join("/seedcache", filename)
                    if os.path.exists(cached_filename):
                        filepath = cached_filename
                    else:
                        # download the file
                        external_filepath = os.path.join(seed_storage_prefix, filename)
                        # download the file
                        # save to cache
                        if os.path.exists(external_filepath):
                            shutil.copy(external_filepath, cached_filename)
                            download_count += 1
                            filepath = cached_filename
                        else:
                            filepath = None
                    # # check if file exists
                    if filepath and filepath not in tarfile_list:
                        # add to tarfile list
                        tarfile_list.append(filepath)
                    # tarfile_list.append(filename)
            logging.info(f'Downloaded {download_count} files from external storage')
            logging.info(f'Got {len(tarfile_list)} files for task {task} and harness {harness}')
        
            # create tarfile
            def create_tarfile():
                # current_time = int(time.time())
                uuid_str = str(uuid.uuid4())
                tarfile_name = f'{task}_{harness}_{uuid_str}.tar.gz'
                tarfile_temp_path = os.path.join("/tmp", tarfile_name)
                tarfile_path = os.path.join(shared_storage_prefix, tarfile_name)
                with tarfile.open(tarfile_temp_path, 'w:gz', compresslevel=0) as tar:
                    for filename in tarfile_list:
                        # add file to tar
                        tar.add(filename, arcname=os.path.basename(filename))
                logging.info(f'Created tarfile {tarfile_name} for task {task} and harness {harness}')
                # move to shared storage
                shutil.move(tarfile_temp_path, tarfile_path)
                logging.info(f'Moved tarfile {tarfile_name} to {tarfile_path}')
                return tarfile_path
            
            tarfile_name = await asyncio.to_thread(create_tarfile)

            # save to redis and local cache
            current_time = int(time.time())
            logging.info(f'Saving tarfile {tarfile_name} to redis and local cache')
            await redis_rw.set(file_cache_key, f'{tarfile_name}:{current_time}')
            local_cache[f'{task}:{harness}'] = (tarfile_name, current_time)
            logging.info(f'Saved tarfile {tarfile_name} to redis and local cache, returning')
            return tarfile_name
        
        # async with lock:
        #     if future_key in futures and not futures[future_key].done():
        #         logging.info(f'There is a future for task {task} and harness {harness} processing, waiting for it')
        #         result = await futures[future_key]
        #         logging.info(f'Awaited future for task {task} and harness {harness}, returning') 
        #         return result
        #     else:
        #         logging.info(f'No future for task {task} and harness {harness}, creating a new future')
        #         future = event_loop.create_future()
        #         futures[future_key] = future
        #         result = await create_and_save_tarfile()
        #         future.set_result(result)
        #         return result
        
        async with lock:
            if future_key not in futures or futures[future_key].done():
                # create a new future 
                future = event_loop.create_future()
                futures[future_key] = future
                asyncio_task = asyncio.create_task(create_and_save_tarfile())
                asyncio_task.add_done_callback(lambda task: futures[future_key].set_result(task.result()))
                

        logging.info(f'Awaiting future for task {task} and harness {harness}')
        result = await futures[future_key]
        logging.info(f'Awaited future for task {task} and harness {harness}, returning')
        return result
        
        # return await create_and_save_tarfile()
        
        # save the tarfile list to redis
        # result = json.dumps(tarfile_list)
        # current_time = int(time.time())
        # await redis_rw.set(file_cache_key, f'{result}:{current_time}')
        # local_cache[f'{task}:{harness}'] = (result, current_time)
        # print(f'Saved tarfile list to redis and local cache, returning')
        # return result
        
    except Exception as e:
        logging.error(f'Internal server error: {e}')
        return False
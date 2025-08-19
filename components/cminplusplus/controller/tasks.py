import logging
import json
import tempfile
import tarfile
import shutil
import os
import asyncio

from executor import run_command

def parse_msg(msg):
    body = msg.body.decode()
    logging.info('Received message: %s', body)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        logging.error('Failed to decode JSON: %s', e)
        return None, None, None
    except Exception as e:
        logging.error('Error processing message: %s', e)
        return None, None, None
    task_id = data.get('task_id', None)
    harness = data.get('harness', None)
    seeds = data.get('seeds', None)
    if task_id is None or harness is None or seeds is None:
        logging.error('Missing required fields in message: %s', data)
        return None, None, None
    logging.info('Task ID: %s', task_id)
    logging.info('Harness: %s', harness)
    logging.info('Seeds: %s', seeds)
    return task_id, harness, seeds


async def save_result(task_id, harness, result, ro_redis, rw_redis):
    # save result to redis
    new_features = 0
    new_features_set = set()
    pipeline = rw_redis.pipeline()
    for feature in result:
        # filename = result[feature]
        # logging.info('Saving result for task %s harness %s feature %d: %s', task_id, harness, feature, filename)
        # save to redis
        key = f'clustercmin:file:{task_id}:{harness}:{feature}'
        # check if key exists
        pipeline.get(key)
    logging.info('Checking if the feature filenames already exist in redis')
    exists_array = await pipeline.execute()
    logging.info('Checking if the feature filenames already exist in redis done')
    
    
    pipeline = rw_redis.pipeline()
    for feature, exists in zip(result.keys(), exists_array):
        if exists:
            continue
        # save to redis
        key = f'clustercmin:file:{task_id}:{harness}:{feature}'
        pipeline.set(key, result[feature])
        # await rw_redis.set_add(f'clustercmin:features:{task_id}:{harness}', feature)
        new_features_set.add(feature)
        new_features += 1
    
    logging.info('Saving the feature filenames to redis')
    await pipeline.execute()
    logging.info('Saving %d new features to redis', new_features)
    if new_features > 0:
        await rw_redis.set_add(f'clustercmin:features:{task_id}:{harness}', new_features_set)
    logging.info('Saved %d new features to redis', new_features)
    

def on_message_wrapper(ro_redis, rw_redis, seed_storage_prefix, msg_queue):
    async def on_message(msg):
        async with msg.process():
            # parse msg
            task_id, harness, seeds = parse_msg(msg)
            if task_id is None or harness is None or seeds is None:
                logging.error('Invalid message, skipping')
                return
            
            key = f'artifacts:{task_id}:{harness}:none:cmin:after'
            logging.info('Getting harness from redis: %s', key)
            harness_path = await ro_redis.get(key)
            if harness_path is None:
                logging.error('Harness not found in redis: %s', key)
                # check if the harness compilation failed
                key = f'artifacts:{task_id}:cmin:failed'
                failed = await ro_redis.get(key)
                if failed is None:
                    logging.error('Harness not found in redis but no failed flag, requeueing')
                    # requeue the task to the end of the rabbitmq queue
                    await asyncio.sleep(5)
                    await msg_queue.send(msg.body.decode())
                    logging.info('Requeued task %s harness %s to the end of the queue', task_id, harness)
                    return
                logging.error('Harness failed to generate, skipping')
                return
            harness_path = harness_path.decode('utf-8')
            logging.info('Harness path: %s', harness_path)
            
            # create workspace in temp dir
            try:
                workspace = tempfile.TemporaryDirectory()
                logging.info('Created workspace for task %s: %s', task_id, workspace.name)
            except Exception as e:
                logging.error('Failed to create workspace: %s', e)
                return

            # copy harness to workspace
            try:
                shutil.copy(harness_path, workspace.name)
                logging.info('Copied harness to %s', workspace.name)
                new_harness_path = os.path.join(workspace.name, os.path.basename(harness_path))
                logging.info('New harness path: %s', new_harness_path)
                # make it executable
                os.chmod(new_harness_path, 0o755)
            except Exception as e:
                logging.error('Failed to copy harness: %s', e)
                # cleanup workspace
                workspace.cleanup()
                return
            
            # extract seeds
            try:
                new_seeds_path = os.path.join(workspace.name, os.path.basename(seeds))
                shutil.copy(seeds, new_seeds_path)
                new_seeds_dir = os.path.join(workspace.name, os.path.basename(seeds).replace('.tar.gz', ''))
                os.makedirs(new_seeds_dir, exist_ok=True)
                logging.info('Copied seeds to %s, extracting', new_seeds_path)
                with tarfile.open(seeds, 'r:gz') as tar:
                    tar.extractall(path=new_seeds_dir)
                    logging.info('Extracted seeds to %s', new_seeds_dir)
                # log the file count
                file_count = len(os.listdir(new_seeds_dir))
                if file_count == 0:
                    logging.error('No files extracted from seeds')
                    # cleanup workspace
                    workspace.cleanup()
                    return
                logging.info('Extracted %d files, copying to seed storage', file_count)
                # copy the seeds to the seed storage prefix
                seeds_storage = seed_storage_prefix
                for filename in os.listdir(new_seeds_dir):
                    src = os.path.join(new_seeds_dir, filename)
                    dst = os.path.join(seeds_storage, filename)
                    shutil.copy(src, dst)
                logging.info('Copied %d files to %s', file_count, seeds_storage)
            except Exception as e:
                logging.error('Failed to extract seeds: %s', e)
                # cleanup workspace
                workspace.cleanup()
                return
            
            # execute cmin
            cmdline = [
                new_harness_path,
                '-generate_hash=1',
                new_seeds_dir,
            ]
            logging.info('Running command line: %s', cmdline)
            
            try:
                stdout, stderr = await run_command(cmdline, cwd=workspace.name, errorable=True, timeout=600)
                # logging.info('Command output: %s', stdout.decode())
                # logging.info('Command error: %s', stderr.decode())
            except Exception as e:
                logging.error('Command failed: %s', e)
                # cleanup workspace
                workspace.cleanup()
                return
            
            # parse result
            # data format: line-based, clustercmin:<feature>:<filename>
            # example: clustercmin:11:test.poc
            result = {}
            filenames = set()
            if b'acd: generate cmin corpus by features in' not in stderr:
                logging.error('Command failed: %s', stderr.decode(errors='ignore'))
                # cleanup workspace
                workspace.cleanup()
                return
            # parse the output
            stderr = stderr[stderr.index(b'acd: generate cmin corpus by features in'):]
            logging.info('Starting to parse %d lines of stderr', len(stderr.decode(errors='ignore').splitlines()))
            for line in stderr.decode(errors='ignore').splitlines():
                if line.startswith('clustercmin:'):
                    parts = line.split(':')
                    if len(parts) != 3:
                        logging.error('Invalid result format: %s', line)
                        continue
                    try:
                        feature = int(parts[1])
                        filename = os.path.basename(parts[2])
                    except ValueError as e:
                        logging.error('Invalid result format: %s', line)
                        continue
                    result[feature] = filename
                    filenames.add(filename)
            logging.info('Features: %d, Files: %d, Minimized to %d%%', len(result), len(filenames), len(filenames) * 100 / file_count)
            # logging.info('Get %d different hashes', len(result))
            # send result to redis
            try:
                logging.info('Saving result to redis')
                # currently we use harness path, so we need to convert it to harness name
                harness_name = os.path.basename(harness)
                await save_result(task_id, harness_name, result, ro_redis, rw_redis)
                logging.info('Saved result to redis')
            except Exception as e:
                logging.error('Failed to save result: %s', e)
                # cleanup workspace
                workspace.cleanup()
                return

            # cleanup workspace
            workspace.cleanup()
            logging.info('Cleaned up workspace for task %s harness %s', task_id, harness)
            logging.info('Finished processing task %s harness %s', task_id, harness)
            return 
    return on_message
       

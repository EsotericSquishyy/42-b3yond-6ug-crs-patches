import threading
import time
import logging
import uuid
import json
import shutil
import os
import tarfile
import pika

from tasks import SarifTaskWorker

from config import Config

from utils.thread import ExceptionThread

class SarifDaemon:
    def __init__(self, msg_queue, debug = False, mock = False):
        self.agent_config = Config()
        self.tasks = []
        self.task_lock = threading.Lock()
        self.msg_queue = msg_queue
        self.task_thread = ExceptionThread(target=self._task_thread)
        self.task_thread.start()
        

    def _task_thread(self):
        # start consume the message queue
        while True:
            try:
                # self.msg_queue.consume(self._on_message)
                self.msg_queue.threaded_consume(self._on_message)
            except pika.exceptions.ConnectionClosed as e:
                logging.error('Connection closed: %s', e)
                # just exit here
                exit(1)
            except Exception as e:
                logging.error('Failed to consume message: %s', e)
                raise e
                # time.sleep(10)

    def _on_message(self, ch, method, properties, body):
        # logging.debug('Received message: %s', body)
        logging.info('New message received')
        # parse the message
        try:
            msg = json.loads(body)
        except Exception as e:
            logging.error('Failed to parse message: %s', e)
            raise e
        
        task_id = msg['task_id']
        sarif_id = msg['sarif_id']
        project_name = msg['project_name']
        focus = msg['focus']
        repos = msg['repo']
        mode = msg['task_type']
        if 'diff' in msg:
            diff = msg['diff']
        else: 
            diff = None
        sarif_report = msg['sarif_report']
        fuzzing_tooling = msg['fuzzing_tooling']

        # create workspace for the task
        worker_id = str(uuid.uuid4())
        logging.info('Creating workspace for task %s <Project %s, SARIF report %s>', task_id, project_name, sarif_id)
        workspace_dir = os.path.join(self.agent_config.tmp_dir, worker_id)
        if os.path.exists(workspace_dir):
            logging.info('Cleaning up workspace: %s', workspace_dir)
            shutil.rmtree(workspace_dir)
        os.makedirs(workspace_dir)

        # copy files to tmp dir
        logging.info('Copying and extracting repos')
        # extracted_repos = []
        for repo in repos:
            # copy repo
            shutil.copy(repo, workspace_dir)
            logging.debug('Copied repo %s to workspace', repo)
            # extract repo
            repo_tar_file = os.path.join(workspace_dir, os.path.basename(repo))
            with tarfile.open(repo_tar_file, 'r:gz') as tar:
                tar.extractall(workspace_dir)
                logging.debug('Extracted repo %s', repo_tar_file)

        # confirm that the focused repo exists
        focused_repo = os.path.join(workspace_dir, focus)
        if not os.path.exists(focused_repo):
            logging.error('Focused repo %s does not exist, what happened?', focused_repo)
            raise Exception('Focused repo does not exist')
        logging.debug('Focused repo: %s', focused_repo)

        # extract the fuzz tooling
        logging.info('Extracting fuzz tooling')
        # extract the fuzz tooling
        with tarfile.open(fuzzing_tooling, 'r:gz') as tar:
            tar.extractall(workspace_dir)
        # TODO: we assume the fuzz tooling is extracted to a folder named fuzz-tooling
        logging.info('Extracted fuzz tooling')

        # save sarif report
        sarif_file = os.path.join(workspace_dir, 'sarif.json')
        # loaded_sarif_report = json.loads(sarif_report)
        with open(sarif_file, 'w') as f:
            f.write(sarif_report)
        logging.debug('Saved SARIF report to %s', sarif_file)

        # save diff if it is delta mode, then apply the diff
        if mode == 'delta':
            logging.info('Delta mode detected')
            # copy and extract diff 
            shutil.copy(diff, workspace_dir)
            diff_tar_file = os.path.join(workspace_dir, os.path.basename(diff))
            with tarfile.open(diff_tar_file, 'r:gz') as tar:
                tar.extractall(workspace_dir)
                logging.debug('Extracted diff %s', diff_tar_file)
            # apply diff, path should be './diff/ref.diff'
            diff_file = os.path.join(workspace_dir, 'diff', 'ref.diff')
            # TODO: currently we just invoke patch command, we may need to implement our own patching logic
            patch_cmd = f'patch -d "{focused_repo}" -p1 < "{diff_file}"'
            logging.debug('Running patch command: %s', patch_cmd)
            os.system(patch_cmd)
            
        else:
            diff_file = None
        
        
        task = SarifTaskWorker(task_id, sarif_id, worker_id, focused_repo, diff_file, sarif_file, original_msg = msg, workspace_dir = workspace_dir)
        
        task.stop()
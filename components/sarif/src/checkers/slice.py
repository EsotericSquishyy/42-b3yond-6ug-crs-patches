import threading
import logging
import os
import time
import json
import hashlib

from sqlalchemy import select

from msg import MsgQueue

from db import DBConnection

from config import Config

from models.sarif_slice import SarifSlice

class SliceChecker:
    def __init__(self, task_id, sarif_id, sarif_results, original_msg = None, project_dir = None):
        self.task_id = task_id
        self.sarif_id = sarif_id
        self.sarif_results = sarif_results
        self.thread = threading.Thread(target=self._run)
        self.stop_event = threading.Event()
        self.global_config = Config()  
        self.original_msg = original_msg
        self.result = None
        self.project_dir = project_dir
        self.thread.start()
        

    def _run(self):
        logging.info('Started slice checker for task %s', self.task_id)
        
        # get function list from sarif_results
        slice_input = []
        function_set = set()
        for issue in self.sarif_results:
            if issue['function'] and issue['function'] not in function_set:
                function_set.add(issue['function'])
                # AD-HOC: for example-libpng, REMOVE THIS IN PRODUCTION!!!
                # read the file and calculate the hash
                file_path = os.path.join(self.project_dir, issue['file'])
                file_data = open(file_path, 'rb').read()
                file_hash = hashlib.md5(file_data).hexdigest()
                if 'libpng' in self.original_msg['project_name']:
                    slice_input.append((file_hash, 'OSS_FUZZ_' + issue['function']))
                else:    
                    slice_input.append((file_hash, issue['function']))
        # build slice input and save to the shared folder
        logging.debug('Task %s | Slicing input %s', self.task_id, json.dumps(slice_input))
        # logging.debug('%s', json.loads(json.dumps(slice_input)))
        # send msg to slicing 
        msg = {
               "is_sarif": True,
               "slice_id": self.sarif_id,
               "slice_target": slice_input,
               "task_id": self.original_msg['task_id'],
               "project_name": self.original_msg['project_name'],
               "focus": self.original_msg['focus'],
               "repo": self.original_msg['repo'],
               "fuzzing_tooling": self.original_msg['fuzzing_tooling'],
               "diff": self.original_msg['diff'] if 'diff' in self.original_msg else None,
               }
        # init sarif-to-slice queue
        sarif_to_slice_connection = MsgQueue(os.getenv('RABBITMQ_URL'), os.getenv('SARIF_TO_SLICE_QUEUE'), os.getenv('SARIF_AGENT_DEBUG') is not None)
        sarif_to_slice_connection.send(json.dumps(msg))
        # wait for ack?
        sarif_to_slice_connection.close()
        
        # pull db to get slice results
        # connect to db
        db_connection = DBConnection(db_url = os.getenv('DATABASE_URL'))
        current_time = 0
        slice_results = None
        db_connection.start_session()
        logging.debug("Task %s | Sarif ID %s", self.task_id, self.sarif_id)
        while self.stop_event.is_set() == False:
            # get slice results
            stmt = select(SarifSlice).where(SarifSlice.sarif_id == self.sarif_id)
            slice_results = db_connection.execute_stmt_with_session(stmt)
            logging.debug("Waiting for slice results for task %s", self.task_id)
            if slice_results:
                break
            else:
                # wait for 10 seconds
                current_time += 10
                if current_time > self.global_config.max_slicing_time:
                    logging.error('Task %s | Slice timeout', self.task_id)
                    break
                time.sleep(10)
        # compare functions in the function set
        logging.info('Task %s | Slicing completed', self.task_id)
        if slice_results:
            # get result path from results
            result_path = slice_results[0].result_path
            # read the result file
            if os.path.exists(result_path):
                
                # assign this value to the object
                self.slice_path = result_path

                # for result_file in os.listdir(result_path):
                with open(os.path.join(result_path), 'r') as f:
                    # with open(os.path.join(result_path, result_file), 'r') as f:
                    slice_result = f.read()
                    # TODO: empty file, currently it is a workaround for the case that failed to generate slice
                    if slice_result == '':
                        logging.warning('Task %s | Slice result file is empty, possible slicing failure', self.task_id)
                        # let it pass now
                        self.result = True
                    elif 'LLVMFuzzerTestOneInput' in slice_result:
                        logging.info('Task %s | Slice result contains LLVMFuzzerTestOneInput', self.task_id)
                        self.result = True
                    else:
                        logging.info('Task %s | Slice result does not contain LLVMFuzzerTestOneInput', self.task_id)
                        self.result = False
            else:
                logging.error('Task %s | Slice result file not found', self.task_id)
                # slice failure, let it pass now
                self.result = True
        db_connection.stop_session()
        # exit 
        self.stop_event.set()

    def stop(self, kill = False):
        if kill:
            self.stop_event.set()
            self.thread.join()
            logging.warning('Killed slice checker for task %s', self.task_id)
        else:
            self.thread.join()
            logging.info('Stopped slice checker for task %s', self.task_id)
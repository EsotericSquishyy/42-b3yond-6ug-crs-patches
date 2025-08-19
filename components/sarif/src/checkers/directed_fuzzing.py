import threading
import logging
import os
import time
import json

from sqlalchemy import select

from msg import MsgQueue

from db import DBConnection

from config import Config

from models.directed_slice import DirectedSlice

class DirectedFuzzingChecker:
    def __init__(self, task_id, sarif_id, sarif_results, original_msg = None, slice_path = None):
        self.task_id = task_id
        self.sarif_id = sarif_id
        self.sarif_results = sarif_results
        self.thread = threading.Thread(target=self._run)
        self.stop_event = threading.Event()
        self.global_config = Config()  
        self.original_msg = original_msg
        self.slice_path = slice_path
        self.result = None
        self.thread.start()
        
        

    def _run(self):
        logging.info('Started directed fuzzing checker for task %s', self.task_id)
        
        # if slice path is None, run slicing 
        if self.slice_path is None:
        # get function list from sarif_results
            slice_input = []
            function_set = set()
            for issue in self.sarif_results:
                if issue['function'] and issue['function'] not in function_set:
                    function_set.add(issue['function'])
                    # AD-HOC: for example-libpng, REMOVE THIS IN PRODUCTION!!!
                    if 'libpng' in self.original_msg['project_name']:
                        slice_input.append((issue['file'], 'OSS_FUZZ_' + issue['function']))
                    else:    
                        slice_input.append((issue['file'], issue['function']))
            # build slice input and save to the shared folder
            logging.debug('Task %s | DF-Slicing input %s', self.task_id, json.dumps(slice_input))
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
            # init queue
            sarif_to_slice_connection = MsgQueue(os.getenv('RABBITMQ_URL'), os.getenv('SLICE_TASK_QUEUE'), os.getenv('SARIF_AGENT_DEBUG') is not None)
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
                stmt = select(DirectedSlice).where(DirectedSlice.directed_id == self.sarif_id)
                slice_results = db_connection.execute_stmt_with_session(stmt)
                logging.debug("Waiting for df-slice results for task %s", self.task_id)
                if slice_results:
                    break
                else:
                    # wait for 10 seconds
                    current_time += 10
                    if current_time > self.global_config.max_slicing_time:
                        logging.error('Task %s | DF-Slice timeout', self.task_id)
                        break
                    time.sleep(10)
            # compare functions in the function set
            slice_path = slice_results[0].result_path
            logging.info('Task %s | DF-Slicing completed, slice at %s', self.task_id, slice_path)
            db_connection.stop_session()
        else:
            logging.info('Task %s | Using previous slice path %s', self.task_id, self.slice_path)
            slice_path = self.slice_path

        if os.path.exists(slice_path):
            # get result path from results
            # read the result file
            # send this to df client
            df_msg = {
                "task_id": self.original_msg['task_id'],
                "task_type": "delta" if self.original_msg['task_type'] == "delta" else "xxy",
                "project_name": self.original_msg['project_name'],
                "focus": self.original_msg['focus'],
                "repo": self.original_msg['repo'],
                "fuzzing_tooling": self.original_msg['fuzzing_tooling'],
                "diff": self.original_msg['diff'] if 'diff' in self.original_msg else None,
                "sarif_slice_path": slice_path
            }
            
            # start mq
            logging.info('Task %s | Sending DF msg', self.task_id)
            df_connection = MsgQueue(os.getenv('RABBITMQ_URL'), os.getenv('CRS_DF_QUEUE'), os.getenv('SARIF_AGENT_DEBUG') is not None)
            df_connection.send(json.dumps(df_msg))
            df_connection.close()
            logging.info('Task %s | DF msg sent', self.task_id)
        else:
            logging.error('Task %s | DF-Slice result file not found', self.task_id)
            self.result = None
        
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
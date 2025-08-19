from mock.mockconfig import MockConfig

from utils.msg import MsgQueue

import logging
import time
import threading
import json
import os
from db.db import DBConnection

# @dataclass
# class DirectedMsg:
#     task_id: str
#     project_name : str
#     focus: str
#     repo: List[str]
#     fuzzing_tooling: str
#     diff: str

def publish_mock_crs_data(id):
    logging.info('Publishing mock data')
    mock_config = MockConfig()
    rabbitmq_url = os.getenv('RABBITMQ_URL', mock_config.rabbitmq_url)
    queue = os.getenv('CRS_DIRECTED_QUEUE', mock_config.crs_directed_queue)
    
    msg = {
        "task_id": 'a804eadc-299e-430f-9812-39f0d85251e9',
        "task_type": 'delta',
        "project_name": mock_config.project_name,
        "focus": mock_config.focus,
        "repo": mock_config.project_urls,
        "fuzzing_tooling": mock_config.fuzzing_tooling,
        "diff": mock_config.diff_url,
        # "sarif_slice_path": '/etc/passwd',
    }
    
    msg = json.dumps(msg)
    
    logging.info('Sending mock crs msg to queue')
    # logging.debug('Sending message to queue: %s', msg)
    
    msg_queue = MsgQueue(rabbitmq_url, queue=queue)
    msg_queue.send(msg)
    msg_queue.close()

def clear_db():
    logging.info('Clearing db')
    mock_config = MockConfig()
    db_connection = DBConnection(db_url = mock_config.db_connection_string)
    db_connection.clear_db()

class MockServer:
    def __init__(self):
        logging.info('Starting mock server')
        self.mock_thread = threading.Thread(target=self._mock_thread)
        self.mock_thread.start()

    def _mock_thread(self):
        time.sleep(1)
        publish_mock_crs_data(1)
        time.sleep(3)

from mockconfig import MockConfig

from msg import MsgQueue

import logging
import time
import threading
import json

from db import DBConnection

from uuid import uuid4

def publish_mock_crs_data(id, rabbitmq_url = None, queue = None):
    logging.info('Publishing mock data')
    mock_config = MockConfig()
    if rabbitmq_url is None:
        rabbitmq_url = mock_config.rabbitmq_url
    if queue is None:
        queue = mock_config.crs_queue
    
    msg = {
        "task_id": str(id),
        "task_type": "full",
        "project_name": mock_config.project_name,
        "focus": mock_config.focus,
        "repo": mock_config.project_urls,
        "fuzzing_tooling": mock_config.fuzzing_tooling, # we don't need this one
        "diff": None, 
        "sarif_id": uuid4().hex,
        "sarif_report": open(mock_config.sarif_file, 'r').read()
    }
    
    msg = json.dumps(msg)
    
    logging.info('Sending mock crs msg to queue')
    # logging.debug('Sending message to queue: %s', msg)
    
    msg_queue = MsgQueue(rabbitmq_url, queue=queue)
    msg_queue.send(msg)
    msg_queue.close()

def publish_mock_slice_data():
    logging.info('Publishing mock data')
    mock_config = MockConfig()  
    host = mock_config.rabbitmq_host
    port = mock_config.rabbitmq_port
    queue = mock_config.crs_queue

def clear_db():
    logging.info('Clearing db')
    mock_config = MockConfig()
    db_connection = DBConnection(db_url = mock_config.db_connection_string)
    db_connection.clear_db()
    

class MockServer:
    def __init__(self):
        logging.info('Starting mock server')
        # clear_db()
        self.mock_thread = threading.Thread(target=self._mock_thread)
        # self.mock_thread.start()

    def _mock_thread(self):
        time.sleep(10)
        publish_mock_crs_data("df2b2459-8e0f-492b-b70b-c01323303bb7")
        # time.sleep(2)
        # publish_mock_crs_data("aabbccdd-dabc-cabd-ddeeff001126")
        # time.sleep(60)
        # publish_mock_crs_data("aabbccdd-dabc-cabd-ddeeff001122")

    def start(self):
        self.mock_thread.start()

    def manual_start(self, url, queue):
        publish_mock_crs_data("df2b2459-8e0f-492b-b70b-c01323303bb7", url, queue)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    mock_server = MockServer()
    mock_server.manual_start("amqp://guest:guest@crs-rabbitmq-S:5672/", "crs-sarif")
    mock_server.mock_thread.join()
    logging.info('Mock server finished')
            
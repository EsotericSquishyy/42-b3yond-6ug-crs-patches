import os
import argparse
import logging
import time
import shutil

from mockconfig import set_mock_env
from mockserver import MockServer

from config import Config

from msg import MsgQueue

from daemon import SarifDaemon

from utils.logs import init_logging

if __name__ == '__main__':
    DEBUG = False
    if 'SARIF_AGENT_DEBUG' in os.environ:
        del os.environ['SARIF_AGENT_DEBUG']
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--mock', action='store_true')
    args = parser.parse_args()
    DEBUG = args.debug
    MOCK = args.mock
    
    if DEBUG: 
        os.environ['SARIF_AGENT_DEBUG'] = '1'

    init_logging(DEBUG)
    
    # What we will have:
    # SARIF report
    # 3 .tar.gz (Project, Diff, FuzzTooling)

    app_config = Config()
    # init tmp dir
    agent_tmp_dir = app_config.tmp_dir
    if os.path.exists(agent_tmp_dir):
        logging.info('Cleaning up tmp dir: %s', agent_tmp_dir)
        shutil.rmtree(agent_tmp_dir)
    os.makedirs(agent_tmp_dir)

    if MOCK:
        logging.warning('Mock mode enabled')
        set_mock_env()
    # Start the message queue daemon
    # TODO: modify here while integrating with the CRS
    logging.getLogger('pika').setLevel(logging.WARNING)
    logging.info('Starting message queue')
    # queue_host = os.getenv('RABBITMQ_HOST')
    queue_name = os.getenv('CRS_QUEUE')
    rabbitmq_url = os.getenv('RABBITMQ_URL')
    # queue_port = os.getenv('RABBITMQ_PORT')
    # # exchange = os.getenv('CRS_EXCHANGE')


    # logging.debug('Queue Host: %s', queue_host)
    # logging.debug('Queue Port: %s', queue_port)
    logging.debug('Queue Name: %s', queue_name)
    # logging.debug('Exchange: %s', exchange)

    if not rabbitmq_url or not queue_name:
        logging.error('RabbitMQ rul/queue name not set')
        exit(1)

    if MOCK:
        # start mock server
        mock_server = MockServer()    
        mock_server.start()
    # connect to msgqueue
    
    try:
        msg_queue = MsgQueue(rabbitmq_url, queue_name, DEBUG)
    except Exception as e:
        logging.error('Failed to connect to message queue: %s', e)
        exit(1)

    # start sarif daemon
    logging.info('Starting SARIF daemon')
    sarif_daemon = SarifDaemon(msg_queue, DEBUG, MOCK)

    # wait for new task
    # logging.info('Waiting for new task')
    # wait new message from the queue
    while True:
        # try:
        #     msg_queue.consume(lambda ch, method, properties, body: logging.info('Received message: %s', body))
        # except Exception as e:
        #     logging.error('Failed to consume message: %s', e)
        time.sleep(10)

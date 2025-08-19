import os
import argparse
import logging
import time
import shutil

from mock.mockconfig import set_mock_env
from mock.mockserver import MockServer

import docker

from config.config import Config

from utils.msg import MsgQueue

from daemon.daemon import SliceDaemon

from utils.logs import init_logging

if __name__ == '__main__':
    DEBUG = False
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--clean', action='store_true')
    args = parser.parse_args()
    DEBUG = args.debug
    MOCK = args.mock
    CLEAN = args.clean

    init_logging(DEBUG)

    app_config = Config()

    if CLEAN:
        # init tmp dir
        agent_tmp_dir = app_config.tmp_dir
        if os.path.exists(agent_tmp_dir):
            logging.info('Cleaning up tmp dir: %s', agent_tmp_dir)
            shutil.rmtree(agent_tmp_dir)
        os.makedirs(agent_tmp_dir)

    # check oss-fuzz-aixcc image
    docker_client = docker.from_env()
    aixcc_images = app_config.DOCKER_IMAGES
    logging.info(aixcc_images)
    
    for image in aixcc_images:
        try:
            docker_client.images.get(image)
        except docker.errors.ImageNotFound:
            logging.error(f'Image Not Found when checking docker images:\n{image}')
            exit(1)
        except Exception as e:
            logging.error(f'Unexcepted error when checking docker images:\n{e}')
            exit(1)

    if MOCK:
        logging.warning('Mock mode enabled')
        set_mock_env()

    # Start the message queue daemon
    logging.getLogger('pika').setLevel(logging.WARNING)
    logging.info('Starting message queue')
    queue_name = os.getenv('SLICE_TASK_QUEUE')
    rabbitmq_url = os.getenv('RABBITMQ_URL')

    logging.debug('Queue Name: %s', queue_name)

    if not rabbitmq_url:
        logging.error('RabbitMQ url not set')
        exit(1)

    if not queue_name:
        logging.error('RabbitMQ queue name not set')
        exit(1)

    if MOCK:
        # start mock server
        mock_server = MockServer()

    # connect to msgqueue
    try:
        msg_queue = MsgQueue(rabbitmq_url, queue_name, DEBUG)
    except Exception as e:
        logging.error('Failed to connect to message queue: %s', e)
        exit(1)
        
    # start directed daemon
    logging.info('Starting Slice daemon')
    directed_daemon = SliceDaemon(msg_queue, DEBUG, MOCK)

    # wait for new task
    while True:
        time.sleep(10)
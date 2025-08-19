from dataclasses import dataclass
import logging
import os
from pathlib import Path

@dataclass
class MockConfig:
    rabbitmq_url = 'amqp://guest:guest@127.0.0.1:55555/'
    # rabbitmq_url = 'amqp://guest:guest@20.42.90.100:5672/'
    crs_directed_queue = 'crs-directed'
    slice_task_queue = 'slice-task'

    project_name = "libexif"
    focus = "libexif"

    test_dir = Path(os.getenv("TEST_DIR")) if os.getenv("TEST_DIR") else Path(__file__).parent.parent.parent / 'tests'
    if not test_dir.exists():
        logging.warning(f"Test directory {test_dir} does not exist, may fail if with --mock set.")

    project_urls = [
        f"{test_dir}/libexif/libexif.tar.gz"
    ]
    diff_url = f"{test_dir}/libexif/DIFF.tar.gz"
    fuzzing_tooling = f"{test_dir}/libexif/fuzz-tooling.tar.gz"

    # postgresql
    db_connection_string = 'postgresql://postgres:popipa@127.0.0.1:45432/directed_test'
    # db_connection_string = 'postgresql://readonly_user:very_secure_password@20.42.90.100:5432/b3yond-db-dev'
    
    # ? For bridge testing
    rabbitmq_url = "amqp://guest:guest@40.90.229.77:5672/"
    db_connection_string = "postgresql://postgres:popopopopopipa@40.90.229.77:5432/directed_test"

def set_mock_env():
    mock_config = MockConfig()
    os.environ['RABBITMQ_URL'] = mock_config.rabbitmq_url
    os.environ['CRS_DIRECTED_QUEUE'] = mock_config.crs_directed_queue
    os.environ['SLICE_TASK_QUEUE'] = mock_config.slice_task_queue
    os.environ['DATABASE_URL'] = mock_config.db_connection_string
from dataclasses import dataclass
import os

@dataclass
class MockConfig:
    # rabbitmq_host = 'localhost'
    # rabbitmq_port = 5672
    # rabbitmq_queue = 'sarif'
    # rabbitmq_url = 'amqp://guest:guest@localhost:5672/'
    # rabbitmq_url = 'amqp://guest:guest@20.42.90.100:5672/'
    rabbitmq_url = 'amqp://guest:guest@crs-rabbitmq-S:5672/'
    crs_exchange = 'crs-exchange'
    crs_queue = 'crs-sarif'
    sarif_to_slice_queue = 'slice-task'
    slice_to_sarif_queue = 'slice-to-sarif'
    sarif_to_df_queue = 'sarif-to-df'
    crs_df_queue = 'crs-directed'
    slice_task_queue = 'slice-task'

    project_name = "libpng"
    # project_dir = './tests/integration/libxml2'
    # sarif_file = './tests/integration/libxml2.sarif'
    # diff_file = './tests/integration/libxml2.diff'
    # focus = "libxml2"
    focus = "example-libpng"
    
    project_urls = [
        # "/home/homura/test/libxml2.tar.gz",
        "/crs/tests/libpng/example-libpng.tar.gz"
        # "/tests/example-libpng.tar.gz"
    ]
    diff_url = "/crs/tests/libpng/diff.tar.gz"
    # diff_url = "/tests/diff-2c894c66108f0724331a9e5b4826e351bf2d094b.tar.gz"
    # diff_url = "/home/homura/test/libxml2.diff.tar.gz"
    # sarif_file = "/crs/tests/libpng/example-libpng.sarif"
    sarif_file = "/crs/tests/libpng/example-libpng-correct.sarif"
    # sarif_file = "/tests/example-libpng.sarif"
    fuzzing_tooling = "/crs/tests/libpng/fuzz-tooling.tar.gz"
    # postgresql
    # db_connection_string = 'postgresql://readonly_user:very_secure_password@localhost:5432/b3yond-db-dev'
    # db_connection_string = 'postgresql://readonly_user:very_secure_password@172.19.0.4:5432/b3yond-db-dev'
    # db_connection_string = 'postgresql://readonly_user:very_secure_password@20.42.90.100:5432/b3yond-db-dev'
    db_connection_string = 'postgresql://postgres:postgres@crs-postgres-S/crs-test'
    # agent_root = '/home/homura/sarif-test/sarif-agent/src'
    agent_root = '/app'
    

def set_mock_env():
    mock_config = MockConfig()
    os.environ['RABBITMQ_URL'] = mock_config.rabbitmq_url
    os.environ['CRS_QUEUE'] = mock_config.crs_queue
    os.environ['SARIF_TO_SLICE_QUEUE'] = mock_config.sarif_to_slice_queue
    # os.environ['SLICE_TO_SARIF_QUEUE'] = mock_config.slice_to_sarif_queue
    # os.environ['SARIF_TO_DF_QUEUE'] = mock_config.sarif_to_df_queue
    os.environ['DATABASE_URL'] = mock_config.db_connection_string
    os.environ['AGENT_ROOT'] = mock_config.agent_root
    os.environ['CRS_DF_QUEUE'] = mock_config.crs_df_queue
    os.environ['SLICE_TASK_QUEUE'] = mock_config.slice_task_queue
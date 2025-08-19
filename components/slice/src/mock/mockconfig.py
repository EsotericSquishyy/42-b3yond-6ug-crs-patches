from dataclasses import dataclass
import logging
import os
from pathlib import Path

@dataclass
class MockConfig:
    rabbitmq_url = 'amqp://guest:guest@127.0.0.1:55555/'
    # rabbitmq_url = 'amqp://guest:guest@20.42.90.100:5672/'
    slice_task_queue = 'slice-task'

    project_name = "libpng"
    focus = "example-libpng"

    test_dir = Path(os.getenv("TEST_DIR")) if os.getenv("TEST_DIR") else Path(__file__).parent.parent.parent / 'tests'
    if not test_dir.exists():
        logging.warning(f"Test directory {test_dir} does not exist, may fail if with --mock set.")

    project_urls = [
        f"{test_dir}/libpng/example-libpng.tar.gz"
    ]
    slice_targets = [["contrib/tools/pngfix.c", "OSS_FUZZ_process_zTXt_iCCP"], ["contrib/tools/pngfix.c", "OSS_FUZZ_zlib_check"], ["pngrtran.c", "OSS_FUZZ_png_init_read_transformations"], ["pngrtran.c", "OSS_FUZZ_png_do_read_invert_alpha"], ["pngrtran.c", "OSS_FUZZ_png_do_read_filler"], ["pngrutil.c", "OSS_FUZZ_png_check_chunk_length"]]
    diff_url = f"{test_dir}/libpng/diff.tar.gz"
    fuzzing_tooling = f"{test_dir}/libpng/fuzz-tooling.tar.gz"

    # postgresql
    db_connection_string = 'postgresql://postgres:popipa@127.0.0.1:45432/directed_test'
    # db_connection_string = 'postgresql://readonly_user:very_secure_password@20.42.90.100:5432/b3yond-db-dev'
    

def set_mock_env():
    mock_config = MockConfig()
    os.environ['RABBITMQ_URL'] = mock_config.rabbitmq_url
    os.environ['SLICE_TASK_QUEUE'] = mock_config.slice_task_queue
    os.environ['DATABASE_URL'] = mock_config.db_connection_string
    os.environ['STORAGE_DIR'] = '/tmp/slice-storage'
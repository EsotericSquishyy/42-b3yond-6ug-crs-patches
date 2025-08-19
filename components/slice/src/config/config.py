from dataclasses import dataclass
import os

@dataclass
class Config:
    DOCKER_IMAGES = [
        'gcr.io/oss-fuzz-base/base-builder:latest',
        'ghcr.io/aixcc-finals/base-builder:latest',
        'ghcr.io/aixcc-finals/base-builder:v1.3.0',
        # 'gcr.io/oss-fuzz-base/base-clang'
    ]
    max_waiting_time = 1800 # seconds
    tmp_dir = '/tmp/crs-slice-agent'
    
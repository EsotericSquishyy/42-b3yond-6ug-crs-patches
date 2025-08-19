from dataclasses import dataclass
import os

@dataclass
class Config:
    max_waiting_time = 1800 # seconds'
    max_slicing_time = 900 # seconds
    tmp_dir = '/tmp/directed-fuzzing-agent'
    
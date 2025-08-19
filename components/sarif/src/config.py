from dataclasses import dataclass
from uuid import uuid4 

# prefix = uuid4()
@dataclass
class Config:
    max_slicing_time = 1200 # seconds
    max_waiting_time = 1800 # seconds
    tmp_dir = '/tmp/sarif-agent'
    
# Directed Fuzzing Service for AIxCC
## How to run on CRS
Six environment variables need to be passed into container:
```
RABBITMQ_URL
DATABASE_URL
SLICE_TASK_QUEUE
SLICE_TASK_QUEUE_R18
REDIS_SENTINEL_HOSTS
REDIS_MASTER
REDIS_PASSWORD
CRS_DIRECTED_QUEUE
STORAGE_DIR
```
One directory need to be passed into container to collect directed output:
```
<CRS_STORAGE_DIR_OUT>:<STORAGE_DIR>
```

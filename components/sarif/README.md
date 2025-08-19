# 42-b3yond-6ug SARIF Agent 

## Usage 

```shell
python3 src/app.py [--mock] [--debug]
```

## Environment Variables

```
RABBITMQ_URL      rabbitmq connection string
CRS_QUEUE         crs queue name
DATABASE_URL      database connection string
SLICE_TASK_QUEUE  slice task queue name 
SARIF_TO_SLICE_QUEUE   slice task queue name
CRS_DF_QUEUE      crs queue name for directed fuzzing 
AGENT_ROOT        root of the agent src
```

## TODOs

- Find a better way to get function name by line number
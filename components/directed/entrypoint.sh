#!/bin/bash
source /opt/bash-utils/logger.sh

# Start docker
INFO "[AIxCC] CRS-DIRECTED"
start-docker.sh

INFO "[AIxCC] running main.py"
python /app/src/app.py # --mock-with-slice
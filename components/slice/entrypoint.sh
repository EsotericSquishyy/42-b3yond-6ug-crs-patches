#!/bin/bash
source /opt/bash-utils/logger.sh

# Start docker
INFO "[AIxCC] CRS-SLICE"
start-docker.sh

# Commands go here
INFO "[AIxCC] loading base-builder image and removing tar"
docker load -i /app/base-builder.tar

# Tag the image
docker tag ghcr.io/aixcc-finals/base-builder:latest gcr.io/oss-fuzz-base/base-builder:latest
docker tag ghcr.io/aixcc-finals/base-builder:v1.3.0 gcr.io/oss-fuzz-base/base-builder:latest
docker tag gcr.io/oss-fuzz-base/base-builder:latest ghcr.io/aixcc-finals/base-builder:latest
docker tag gcr.io/oss-fuzz-base/base-builder:latest ghcr.io/aixcc-finals/base-builder:v1.3.0
# docker tag gcr.io/oss-fuzz-base/base-builder:latest ghcr.io/aixcc-finals/base-builder:v1.2.0
# docker tag gcr.io/oss-fuzz-base/base-builder:latest ghcr.io/aixcc-finals/base-builder:v1.2.2
# docker tag gcr.io/oss-fuzz-base/base-builder:latest ghcr.io/aixcc-finals/base-builder:v1.3.0
# rm /app/base-builder.tar

INFO "[AIxCC] running main.py"
python /app/src/app.py --debug
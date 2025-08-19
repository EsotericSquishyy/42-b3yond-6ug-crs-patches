#!/bin/bash

docker compose up -d  dev-redis-master
echo "Waiting for Redis IP:"

docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' dev-redis-master

sleep 5

docker compose up -d --build


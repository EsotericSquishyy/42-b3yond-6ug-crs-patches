#!/bin/bash
set -o allexport
source .env
set +o allexport

DURATION=14400

curl -v \
  -u "$COMPETITION_API_KEY_ID:$COMPETITION_API_KEY_TOKEN" \
  -X 'POST' \
  https://virtual-echo.tasker.aixcc.tech/v1/request/delta/ \
  -H "Content-Type: application/json" \
  -d "{\"duration_secs\": $DURATION}" \
  -w "\nHTTP Status: %{http_code}\n"

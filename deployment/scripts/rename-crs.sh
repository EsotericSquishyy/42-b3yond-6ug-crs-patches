#!/bin/bash

set -o allexport
source .env
set +o allexport

FQDN=$(kubectl get ingress | awk 'NR>1 {print $4}')
HOSTNAME=$(echo $FQDN | cut -d'.' -f1)

if [ -z "$HOSTNAME" ]; then
  echo "No hostname found in ingress. Exiting."
  exit 1
fi

curl -u "$COMPETITION_API_KEY_ID:$COMPETITION_API_KEY_TOKEN" \
  -X PATCH \
  https://virtual-echo.tasker.aixcc.tech/tailscale/device/$HOSTNAME \
  -H 'Content-Type: application/json' -d '{"hostname":"virtual-echo-exhibition3"}'

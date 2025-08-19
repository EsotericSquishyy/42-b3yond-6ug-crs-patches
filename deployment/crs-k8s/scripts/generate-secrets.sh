#!/bin/bash

# Source the .env file if it exists
if [ -f ".env" ]; then
  echo "Loading credentials from .env file..."
  source .env
else
  echo "Error: .env file not found in the current directory."
  echo "Please create a .env file with the required variables."
  exit 1
fi

# Define required variables
REQUIRED_VARS=(
  "GITHUB_USERNAME"
  "GITHUB_TOKEN"
  "GITHUB_EMAIL"
  "TS_CLIENT_ID"
  "TS_CLIENT_SECRET"
  "TS_OP_TAG"
  "TS_HOSTNAME"
  "CRS_API_HOSTNAME"
  "OTEL_EXPORTER_OTLP_ENDPOINT"
  # "OTEL_EXPORTER_OTLP_HEADERS" -- this can be empty
  "OTEL_EXPORTER_OTLP_PROTOCOL"
  "COMPETITION_API_URL"
  "COMPETITION_API_KEY_ID"
  "COMPETITION_API_KEY_TOKEN"
  "CRS_KEY_ID"
  "CRS_KEY_TOKEN"
  # API Keys for Litellm
  "OPENAI_API_KEY"
  "ANTHROPIC_API_KEY"
  "DEEPSEEK_API_KEY"
  "GOOGLE_API_KEY"
)

# Check if required variables are set
missing_vars=()
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var}" ]; then
    missing_vars+=("$var")
  fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
  echo "Error: The following required variables are missing in the .env file:"
  printf '%s\n' "${missing_vars[@]}"
  exit 1
fi

# Check if DB_CONNECTION_STRING is set as an environment variable
if [ -z "$DB_CONNECTION_STRING" ]; then
  echo "Error: DB_CONNECTION_STRING environment variable is not set."
  echo "This should be set when calling the script."
  exit 1
fi

if [ -z "$LITELLM_CONNECTION_STRING" ]; then
  echo "Error: LITELLM_CONNECTION_STRING environment variable is not set."
  echo "This should be set when calling the script."
  exit 1
fi

# Generate the dockerconfigjson
if [ -z "$DOCKERHUB_PASSWORD" ]; then
  DOCKER_CONFIG=$(echo -n '{"auths":{"ghcr.io":{"username":"'$GITHUB_USERNAME'","password":"'$GITHUB_TOKEN'","email":"'$GITHUB_EMAIL'","auth":"'$(echo -n "$GITHUB_USERNAME:$GITHUB_TOKEN" | base64 -w0)'"}}}' | base64 -w0)
else
  DOCKER_CONFIG=$(echo -n '{
    "auths": {
      "ghcr.io": {
        "username": "'$GITHUB_USERNAME'",
        "password": "'$GITHUB_TOKEN'",
        "email": "'$GITHUB_EMAIL'",
        "auth": "'$(echo -n "$GITHUB_USERNAME:$GITHUB_TOKEN" | base64 -w0)'"
      },
      "https://index.docker.io/v1/": {
        "username": "'$DOCKERHUB_USERNAME'",
        "password": "'$DOCKERHUB_PASSWORD'",
        "email": "'$DOCKERHUB_EMAIL'",
        "auth": "'$(echo -n "$DOCKERHUB_USERNAME:$DOCKERHUB_PASSWORD" | base64 -w0)'"
      }
    }
  }' | base64 -w0)
fi

# Create the secret-values.yaml file
cat >$(dirname "$0")/../b3yond-crs/secret-values.yaml <<EOF
imagePullSecrets:
  name: ghcr-registry
  dockerconfigjson: |
    $DOCKER_CONFIG

global:
  otel:
    endpoint: "$OTEL_EXPORTER_OTLP_ENDPOINT"
    headers: "$OTEL_EXPORTER_OTLP_HEADERS"
    protocol: "$OTEL_EXPORTER_OTLP_PROTOCOL"
  database:
    connectionString: "$DB_CONNECTION_STRING"
  competition:
    url: "$COMPETITION_API_URL"
    apiUser: "$COMPETITION_API_KEY_ID"
    apiKey: "$COMPETITION_API_KEY_TOKEN"
  crs:
    hostname: "$CRS_API_HOSTNAME"
    apiUser: "$CRS_KEY_ID"
    apiKey: "$CRS_KEY_TOKEN"
  openaiApiKey: "$OPENAI_API_KEY"
  anthropicApiKey: "$ANTHROPIC_API_KEY"
  deepseekApiKey: "$DEEPSEEK_API_KEY"
  googleApiKey: "$GOOGLE_API_KEY"

tailscale-operator:
  oauth:
    clientId: "$TS_CLIENT_ID"
    clientSecret: "$TS_CLIENT_SECRET"
  operatorConfig:
    defaultTags:
      - "$TS_OP_TAG"
    hostname: "$TS_HOSTNAME"
  proxyConfig:
    defaultTags: "$TS_OP_TAG"

litellm:
  database:
    connectionString: "$LITELLM_CONNECTION_STRING"
EOF

echo "secret-values.yaml has been generated successfully!"

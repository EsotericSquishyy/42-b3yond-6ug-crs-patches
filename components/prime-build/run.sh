#!/bin/sh

# If .env file exists, export environment variables from it
if [ -f "$(dirname "$0")/.env" ]; then
  export $(grep -v '^#' "$(dirname "$0")/.env" | xargs)
fi

# This script is used to run the Python script with the specified arguments.
python -m primebuilder.main "$@"
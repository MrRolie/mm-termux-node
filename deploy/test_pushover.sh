#!/bin/bash
# Send a test Pushover notification from the Termux node
# Run this on the phone after deployment

set -e

# Determine project root
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"

if [ -f "${ENV_FILE}" ]; then
    source "${ENV_FILE}"
else
    echo "Error: .env not found at ${ENV_FILE}. Create it with PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN."
    exit 1
fi

if [ -z "${PUSHOVER_USER_KEY}" ] || [ -z "${PUSHOVER_API_TOKEN}" ]; then
    echo "Error: PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN must be set in ${ENV_FILE}"
    exit 1
fi

echo "Sending test notification to user ${PUSHOVER_USER_KEY}..."

if command -v curl >/dev/null 2>&1; then
    resp=$(curl -s -F "token=${PUSHOVER_API_TOKEN}" \
                -F "user=${PUSHOVER_USER_KEY}" \
                -F "title=TrendForce Test" \
                -F "message=Test message from mm-termux-node" \
                https://api.pushover.net/1/messages.json)
    echo "Response: ${resp}"
    if echo "${resp}" | grep -q '"status":1'; then
        echo "Success: notification delivered.";
        exit 0
    else
        echo "Failure: check response above and ensure device is online and Pushover app is logged in.";
        exit 2
    fi
elif command -v python >/dev/null 2>&1; then
    python - <<PY
import os, json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

token=os.environ.get('PUSHOVER_API_TOKEN')
user=os.environ.get('PUSHOVER_USER_KEY')
req = Request(
    "https://api.pushover.net/1/messages.json",
    data=urlencode({"token":token,"user":user,"title":"TrendForce Test","message":"Test message from mm-termux-node"}).encode(),
    method="POST"
)
req.add_header("Content-Type","application/x-www-form-urlencoded")
print(json.loads(urlopen(req, timeout=30).read().decode()))
PY
else
    echo "Error: neither 'curl' nor 'python' found. Install curl with 'pkg install curl' or run with Python available."
    exit 3
fi

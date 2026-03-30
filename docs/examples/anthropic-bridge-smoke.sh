#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${FAIGATE_BASE_URL:-http://127.0.0.1:8090}"
MODEL_ALIAS="${FAIGATE_ANTHROPIC_MODEL_ALIAS:-claude-code}"

echo "==> Health"
rtk curl -fsS "${BASE_URL}/health"
printf '\n\n'

echo "==> Anthropic messages"
rtk curl -fsS "${BASE_URL}/v1/messages" \
  -H 'Content-Type: application/json' \
  -H 'anthropic-client: claude-code' \
  -d "{
    \"model\": \"${MODEL_ALIAS}\",
    \"system\": \"Respond as a concise operator helper.\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Summarize why one local gateway endpoint helps with Anthropic quota limits.\"}
    ]
  }"
printf '\n\n'

echo "==> Anthropic count_tokens"
rtk curl -i -fsS "${BASE_URL}/v1/messages/count_tokens" \
  -H 'Content-Type: application/json' \
  -d "{
    \"model\": \"${MODEL_ALIAS}\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Count the bridge tokens for this request.\"}
    ]
  }"
printf '\n'

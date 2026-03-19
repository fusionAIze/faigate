#!/usr/bin/env bash
# Example environment for OpenAI-compatible CLI tools using fusionAIze Gate.

export OPENAI_BASE_URL="http://127.0.0.1:8090/v1"
export OPENAI_API_KEY="local"
export FAIGATE_CLIENT_HEADER="X-faigate-Client: codex"

# Example one-off request:
# curl -fsS "$OPENAI_BASE_URL/chat/completions" \
#   -H "Content-Type: application/json" \
#   -H "$FAIGATE_CLIENT_HEADER" \
#   -d '{
#     "model": "auto",
#     "messages": [{"role": "user", "content": "Describe the current gateway health."}]
#   }'

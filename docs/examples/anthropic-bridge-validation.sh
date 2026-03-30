set -euo pipefail

BASE_URL="${FAIGATE_BASE_URL:-http://127.0.0.1:8090}"
MODEL_ALIAS="${FAIGATE_ANTHROPIC_MODEL_ALIAS:-claude-code}"

echo "==> Health"
rtk curl -fsS "${BASE_URL}/health"
printf '\n\n'

echo "==> Provider inventory"
rtk curl -fsS "${BASE_URL}/api/providers"
printf '\n\n'

echo "==> Anthropic messages with bridge headers"
rtk curl -i -fsS "${BASE_URL}/v1/messages" \
  -H 'Content-Type: application/json' \
  -H 'anthropic-client: claude-code' \
  -H 'anthropic-version: 2023-06-01' \
  -H 'anthropic-beta: tools-2024-04-04' \
  -d "{
    \"model\": \"${MODEL_ALIAS}\",
    \"system\": \"Respond as a concise operator helper.\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Summarize why one local gateway endpoint helps with Anthropic quota limits.\"}
    ]
  }"
printf '\n\n'

echo "==> Anthropic tool roundtrip shape"
rtk curl -i -fsS "${BASE_URL}/v1/messages" \
  -H 'Content-Type: application/json' \
  -H 'anthropic-client: claude-code' \
  -d "{
    \"model\": \"${MODEL_ALIAS}\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Load the deployment guide.\"},
      {
        \"role\": \"assistant\",
        \"content\": [
          {
            \"type\": \"tool_use\",
            \"id\": \"toolu_demo\",
            \"name\": \"lookup_doc\",
            \"input\": {\"id\": \"deploy-guide\"}
          }
        ]
      },
      {
        \"role\": \"user\",
        \"content\": [
          {
            \"type\": \"tool_result\",
            \"tool_use_id\": \"toolu_demo\",
            \"content\": \"Deployment guide loaded successfully.\"
          }
        ]
      }
    ]
  }"
printf '\n\n'

echo "==> Anthropic count_tokens"
rtk curl -i -fsS "${BASE_URL}/v1/messages/count_tokens" \
  -H 'Content-Type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -d "{
    \"model\": \"${MODEL_ALIAS}\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Count the bridge tokens for this request.\"}
    ]
  }"
printf '\n\n'

echo "==> Doctor"
./scripts/faigate-doctor
printf '\n\n'

echo "==> Provider probe"
./scripts/faigate-provider-probe --json
printf '\n'

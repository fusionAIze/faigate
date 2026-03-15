#!/usr/bin/env node

const args = process.argv.slice(2);

function usage() {
  console.log(`FoundryGate CLI

Usage:
  foundrygate-cli health [--base-url URL]
  foundrygate-cli models [--base-url URL]
  foundrygate-cli update [--base-url URL] [--force]
  foundrygate-cli route --message TEXT [--base-url URL] [--model MODEL] [--client TAG]

Environment:
  FOUNDRYGATE_BASE_URL  Override the gateway base URL (default: http://127.0.0.1:8090)
`);
}

function readOption(name, fallback = "") {
  const index = args.indexOf(name);
  if (index === -1 || index === args.length - 1) return fallback;
  return args[index + 1];
}

function hasFlag(name) {
  return args.includes(name);
}

function commandName() {
  return args[0] || "";
}

function baseUrl() {
  const raw = readOption("--base-url", process.env.FOUNDRYGATE_BASE_URL || "http://127.0.0.1:8090");
  return raw.replace(/\/+$/, "");
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${baseUrl()}${path}`, options);
  const text = await response.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = { raw: text };
  }
  if (!response.ok) {
    const error = new Error(`Request failed with HTTP ${response.status}`);
    error.response = body;
    throw error;
  }
  return body;
}

async function run() {
  const command = commandName();
  if (!command || hasFlag("--help") || hasFlag("-h")) {
    usage();
    return;
  }

  if (command === "health") {
    console.log(JSON.stringify(await requestJson("/health"), null, 2));
    return;
  }

  if (command === "models") {
    console.log(JSON.stringify(await requestJson("/v1/models"), null, 2));
    return;
  }

  if (command === "update") {
    const suffix = hasFlag("--force") ? "?force=true" : "";
    console.log(JSON.stringify(await requestJson(`/api/update${suffix}`), null, 2));
    return;
  }

  if (command === "route") {
    const message = readOption("--message");
    if (!message) {
      throw new Error("route requires --message");
    }
    const model = readOption("--model", "auto");
    const clientTag = readOption("--client", "");
    const headers = { "content-type": "application/json" };
    if (clientTag) {
      headers["x-foundrygate-client"] = clientTag;
    }
    const body = {
      model,
      messages: [{ role: "user", content: message }]
    };
    console.log(
      JSON.stringify(
        await requestJson("/api/route", {
          method: "POST",
          headers,
          body: JSON.stringify(body)
        }),
        null,
        2
      )
    );
    return;
  }

  throw new Error(`Unknown command '${command}'`);
}

run().catch((error) => {
  console.error(error.message);
  if (error.response) {
    console.error(JSON.stringify(error.response, null, 2));
  }
  process.exit(1);
});

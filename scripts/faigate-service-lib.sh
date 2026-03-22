#!/usr/bin/env bash
set -euo pipefail

faigate_script_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

faigate_repo_root() {
  cd "$(faigate_script_dir)/.." && pwd
}

faigate_platform() {
  uname -s
}

faigate_brew_bin() {
  if [ -x "/opt/homebrew/bin/brew" ]; then
    printf '%s\n' "/opt/homebrew/bin/brew"
  elif [ -x "/usr/local/bin/brew" ]; then
    printf '%s\n' "/usr/local/bin/brew"
  else
    printf '%s\n' "brew"
  fi
}

faigate_python_bin() {
  if [ -n "${FAIGATE_PYTHON:-}" ]; then
    printf '%s\n' "$FAIGATE_PYTHON"
  elif [ -x "$(faigate_repo_root)/.venv/bin/python" ]; then
    printf '%s\n' "$(faigate_repo_root)/.venv/bin/python"
  else
    printf '%s\n' "python3"
  fi
}

faigate_mac_label() {
  if faigate_is_homebrew_runtime; then
    printf '%s\n' "homebrew.mxcl.faigate"
  else
    printf '%s\n' "com.fusionaize.faigate"
  fi
}

faigate_mac_gui_domain() {
  printf 'gui/%s\n' "$(id -u)"
}

faigate_mac_agent_dir() {
  printf '%s\n' "${FAIGATE_MAC_AGENT_DIR:-$HOME/Library/LaunchAgents}"
}

faigate_mac_plist_path() {
  printf '%s/%s.plist\n' "$(faigate_mac_agent_dir)" "$(faigate_mac_label)"
}

faigate_mac_config_dir() {
  printf '%s\n' "${FAIGATE_MAC_CONFIG_DIR:-$HOME/Library/Application Support/faigate}"
}

faigate_mac_logs_dir() {
  printf '%s\n' "${FAIGATE_MAC_LOGS_DIR:-$HOME/Library/Logs/faigate}"
}

faigate_brew_prefix() {
  local config_file
  config_file="$(faigate_config_file)"
  case "$config_file" in
    */etc/faigate/*)
      printf '%s\n' "${config_file%/etc/faigate/*}"
      return 0
      ;;
  esac

  if [ -x "$(faigate_brew_bin)" ]; then
    "$(faigate_brew_bin)" --prefix 2>/dev/null || true
  fi
}

faigate_is_homebrew_runtime() {
  if [ "$(faigate_platform)" != "Darwin" ]; then
    return 1
  fi

  case "$(faigate_script_dir)" in
    */Cellar/faigate/*|*/opt/faigate/share/faigate/scripts)
      return 0
      ;;
  esac

  case "$(faigate_config_file)" in
    /opt/homebrew/etc/faigate/*|/usr/local/etc/faigate/*)
      return 0
      ;;
  esac

  return 1
}

faigate_mac_db_path() {
  printf '%s/faigate.db\n' "$(faigate_mac_config_dir)"
}

faigate_mac_python() {
  printf '%s/.venv/bin/python\n' "$(faigate_repo_root)"
}

faigate_mac_config_path() {
  printf '%s/config.yaml\n' "$(faigate_mac_config_dir)"
}

faigate_config_file() {
  if [ -n "${FAIGATE_CONFIG_FILE:-}" ]; then
    printf '%s\n' "$FAIGATE_CONFIG_FILE"
  else
    printf '%s/config.yaml\n' "$(faigate_repo_root)"
  fi
}

faigate_env_file() {
  if [ -n "${FAIGATE_ENV_FILE:-}" ]; then
    printf '%s\n' "$FAIGATE_ENV_FILE"
  else
    printf '%s/.env\n' "$(faigate_repo_root)"
  fi
}

faigate_example_env_file() {
  printf '%s/.env.example\n' "$(faigate_repo_root)"
}

faigate_env_value() {
  local key="$1"
  local env_file
  env_file="$(faigate_env_file)"
  if [ ! -f "$env_file" ]; then
    return 1
  fi
  awk -F= -v key="$key" '
    $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
      sub(/^[[:space:]]+/, "", $2)
      gsub(/^"|"$/, "", $2)
      print $2
    }
  ' "$env_file" | tail -n 1
}

faigate_yaml_value() {
  local dotted_key="$1"
  local default="${2:-}"
  local config_file python_bin
  config_file="$(faigate_config_file)"
  python_bin="$(faigate_python_bin)"
  if [ ! -f "$config_file" ]; then
    printf '%s\n' "$default"
    return 0
  fi

  FAIGATE_YAML_FILE="$config_file" \
    FAIGATE_YAML_KEY="$dotted_key" \
    FAIGATE_YAML_DEFAULT="$default" \
    "$python_bin" - <<'PY'
import os
from pathlib import Path

import yaml

config_path = Path(os.environ["FAIGATE_YAML_FILE"])
dotted_key = os.environ["FAIGATE_YAML_KEY"]
default = os.environ.get("FAIGATE_YAML_DEFAULT", "")

if not config_path.exists():
    print(default)
    raise SystemExit(0)

with config_path.open(encoding="utf-8") as handle:
    raw = yaml.safe_load(handle) or {}

value = raw
for segment in dotted_key.split("."):
    if not isinstance(value, dict) or segment not in value:
        print(default)
        raise SystemExit(0)
    value = value[segment]

if value is None:
    print(default)
elif isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
}

faigate_host() {
  printf '%s\n' "${FAIGATE_HOST:-$(faigate_yaml_value server.host "127.0.0.1")}"
}

faigate_local_host() {
  local host
  host="$(faigate_host)"
  case "$host" in
    0.0.0.0|"::"|"[::]"|"::0")
      printf '%s\n' "127.0.0.1"
      ;;
    *)
      printf '%s\n' "$host"
      ;;
  esac
}

faigate_port() {
  if [ -n "${FAIGATE_PORT:-}" ]; then
    printf '%s\n' "$FAIGATE_PORT"
    return 0
  fi
  local env_port
  env_port="$(faigate_env_value FAIGATE_PORT 2>/dev/null || true)"
  if [ -n "$env_port" ]; then
    printf '%s\n' "$env_port"
  else
    printf '%s\n' "$(faigate_yaml_value server.port "8090")"
  fi
}

faigate_log_level() {
  printf '%s\n' "$(faigate_yaml_value server.log_level "info")"
}

faigate_db_path() {
  if [ -n "${FAIGATE_DB_PATH:-}" ]; then
    printf '%s\n' "$FAIGATE_DB_PATH"
    return 0
  fi
  local env_db
  env_db="$(faigate_env_value FAIGATE_DB_PATH 2>/dev/null || true)"
  if [ -n "$env_db" ]; then
    printf '%s\n' "$env_db"
  elif [ "$(faigate_platform)" = "Darwin" ] && [ -n "${FAIGATE_MAC_CONFIG_DIR:-}" ]; then
    faigate_mac_db_path
  else
    printf '%s\n' "$(faigate_repo_root)/faigate.db"
  fi
}

faigate_health_url() {
  printf 'http://%s:%s/health\n' "$(faigate_local_host)" "$(faigate_port)"
}

faigate_models_url() {
  printf 'http://%s:%s/v1/models\n' "$(faigate_local_host)" "$(faigate_port)"
}

faigate_update_url() {
  printf 'http://%s:%s/api/update\n' "$(faigate_local_host)" "$(faigate_port)"
}

faigate_stats_url() {
  printf 'http://%s:%s/api/stats\n' "$(faigate_local_host)" "$(faigate_port)"
}

faigate_provider_inventory_url() {
  printf 'http://%s:%s/api/providers\n' "$(faigate_local_host)" "$(faigate_port)"
}

faigate_service_manager() {
  case "$(faigate_platform)" in
    Darwin)
      if faigate_is_homebrew_runtime; then
        printf '%s\n' "brew services (launchd)"
      else
        printf '%s\n' "launchd"
      fi
      ;;
    *)
      printf '%s\n' "systemd"
      ;;
  esac
}

faigate_service_target() {
  case "$(faigate_platform)" in
    Darwin)
      printf '%s\n' "$(faigate_mac_label)"
      ;;
    *)
      printf '%s\n' "faigate.service"
      ;;
  esac
}

faigate_logs_stdout_path() {
  case "$(faigate_platform)" in
    Darwin)
      if faigate_is_homebrew_runtime; then
        printf '%s/var/log/faigate/output.log\n' "$(faigate_brew_prefix)"
      else
        printf '%s/stdout.log\n' "$(faigate_mac_logs_dir)"
      fi
      ;;
    *)
      printf '%s\n' "journalctl://faigate.service"
      ;;
  esac
}

faigate_logs_stderr_path() {
  case "$(faigate_platform)" in
    Darwin)
      if faigate_is_homebrew_runtime; then
        printf '%s/var/log/faigate/error.log\n' "$(faigate_brew_prefix)"
      else
        printf '%s/stderr.log\n' "$(faigate_mac_logs_dir)"
      fi
      ;;
    *)
      printf '%s\n' "journalctl://faigate.service"
      ;;
  esac
}

faigate_service_state() {
  case "$(faigate_platform)" in
    Darwin)
      if faigate_is_homebrew_runtime; then
        local brew_state
        brew_state="$("$(faigate_brew_bin)" services list 2>/dev/null | awk '$1=="faigate" {print $2; exit}')"
        if [ -n "$brew_state" ]; then
          printf '%s\n' "$brew_state"
          return 0
        fi
      fi
      local state_line
      state_line="$(faigate_launchctl_status 2>/dev/null | awk -F'= ' '/state = / {gsub(/;$/, "", $2); print $2; exit}')"
      if [ -n "$state_line" ]; then
        printf '%s\n' "$state_line"
      elif [ -f "$(faigate_mac_plist_path)" ]; then
        printf '%s\n' "configured"
      else
        printf '%s\n' "not loaded"
      fi
      ;;
    *)
      systemctl is-active faigate.service 2>/dev/null || printf '%s\n' "inactive"
      ;;
  esac
}

faigate_service_enabled_state() {
  case "$(faigate_platform)" in
    Darwin)
      if faigate_is_homebrew_runtime; then
        printf '%s\n' "managed by brew services"
      elif [ -f "$(faigate_mac_plist_path)" ]; then
        printf '%s\n' "configured"
      else
        printf '%s\n' "absent"
      fi
      ;;
    *)
      systemctl is-enabled faigate.service 2>/dev/null || printf '%s\n' "disabled"
      ;;
  esac
}

faigate_is_healthy() {
  curl -fsS -m 2 "$(faigate_health_url)" >/dev/null 2>&1
}

faigate_wait_for_health() {
  local timeout_seconds="${1:-15}"
  local attempt=0
  while [ "$attempt" -lt "$timeout_seconds" ]; do
    if faigate_is_healthy; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  return 1
}

faigate_mask_secret() {
  local value="${1:-}"
  local len="${#value}"
  if [ "$len" -le 6 ]; then
    printf '%s\n' "${value:-not set}"
  else
    printf '%s***%s\n' "${value:0:3}" "${value: -3}"
  fi
}

faigate_bin_dir() {
  case "$(faigate_platform)" in
    Darwin)
      printf '%s\n' "${FAIGATE_BIN_DIR:-$HOME/.local/bin}"
      ;;
    *)
      printf '%s\n' "${FAIGATE_BIN_DIR:-/usr/local/bin}"
      ;;
  esac
}

faigate_install_helper_links() {
  local repo_root target_bin helper
  repo_root="$(faigate_repo_root)"
  target_bin="$(faigate_bin_dir)"
  mkdir -p "$target_bin"
  for helper in "$@"; do
    ln -sf "$repo_root/scripts/$helper" "$target_bin/$helper"
  done
  printf 'helper links installed in: %s\n' "$target_bin"
}

faigate_remove_helper_links() {
  local target_bin helper
  target_bin="$(faigate_bin_dir)"
  for helper in "$@"; do
    rm -f "$target_bin/$helper"
  done
  printf 'removed helper links from: %s\n' "$target_bin"
}

faigate_render_mac_plist() {
  local repo_root template target config_dir logs_dir
  repo_root="$(faigate_repo_root)"
  template="$repo_root/docs/examples/com.fusionaize.faigate.plist"
  target="$(faigate_mac_plist_path)"
  config_dir="$(faigate_mac_config_dir)"
  logs_dir="$(faigate_mac_logs_dir)"
  mkdir -p "$(faigate_mac_agent_dir)" "$config_dir" "$logs_dir"
  sed "s|/Users/REPLACE_ME|$HOME|g" "$template" >"$target"
  printf 'launchd plist written to: %s\n' "$target"
}

faigate_launchctl_bootout() {
  local domain label plist
  domain="$(faigate_mac_gui_domain)"
  label="$(faigate_mac_label)"
  plist="$(faigate_mac_plist_path)"
  if faigate_is_homebrew_runtime; then
    launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
    return 0
  fi
  launchctl bootout "$domain/$label" >/dev/null 2>&1 || launchctl bootout "$domain" "$plist" >/dev/null 2>&1 || true
}

faigate_launchctl_start() {
  local domain label plist
  domain="$(faigate_mac_gui_domain)"
  label="$(faigate_mac_label)"
  plist="$(faigate_mac_plist_path)"
  if faigate_is_homebrew_runtime; then
    "$(faigate_brew_bin)" services restart faigate
    return 0
  fi
  faigate_launchctl_bootout
  launchctl bootstrap "$domain" "$plist"
  launchctl kickstart -k "$domain/$label"
}

faigate_launchctl_stop() {
  if faigate_is_homebrew_runtime; then
    "$(faigate_brew_bin)" services stop faigate
    return 0
  fi
  faigate_launchctl_bootout
}

faigate_launchctl_status() {
  local domain label
  domain="$(faigate_mac_gui_domain)"
  label="$(faigate_mac_label)"
  if faigate_is_homebrew_runtime; then
    launchctl print "$domain/$label"
    return 0
  fi
  launchctl print "$domain/$label"
}

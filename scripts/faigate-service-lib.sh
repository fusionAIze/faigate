#!/usr/bin/env bash
set -euo pipefail

faigate_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

faigate_platform() {
  uname -s
}

faigate_mac_label() {
  printf '%s\n' "com.fusionaize.faigate"
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

faigate_mac_db_path() {
  printf '%s/faigate.db\n' "$(faigate_mac_config_dir)"
}

faigate_mac_python() {
  printf '%s/.venv/bin/python\n' "$(faigate_repo_root)"
}

faigate_mac_config_path() {
  printf '%s/config.yaml\n' "$(faigate_mac_config_dir)"
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
  launchctl bootout "$domain/$label" >/dev/null 2>&1 || launchctl bootout "$domain" "$plist" >/dev/null 2>&1 || true
}

faigate_launchctl_start() {
  local domain label plist
  domain="$(faigate_mac_gui_domain)"
  label="$(faigate_mac_label)"
  plist="$(faigate_mac_plist_path)"
  faigate_launchctl_bootout
  launchctl bootstrap "$domain" "$plist"
  launchctl kickstart -k "$domain/$label"
}

faigate_launchctl_stop() {
  faigate_launchctl_bootout
}

faigate_launchctl_status() {
  local domain label
  domain="$(faigate_mac_gui_domain)"
  label="$(faigate_mac_label)"
  launchctl print "$domain/$label"
}

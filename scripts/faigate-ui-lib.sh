#!/usr/bin/env bash
set -euo pipefail

FAIGATE_UI_RESET=$'\033[0m'
FAIGATE_UI_BOLD=$'\033[1m'
FAIGATE_UI_DIM=$'\033[2m'
FAIGATE_UI_CYAN=$'\033[36m'
FAIGATE_UI_GREEN=$'\033[32m'
FAIGATE_UI_YELLOW=$'\033[33m'
FAIGATE_UI_RED=$'\033[31m'

faigate_ui_clear() {
  if [ -t 1 ] && command -v clear >/dev/null 2>&1; then
    clear
  fi
}

faigate_ui_header() {
  local title="${1:-fusionAIze Gate}"
  local subtitle="${2:-}"
  faigate_ui_clear
  printf "\n"
  printf "  %s\n" "▐▘    ▘    ▄▖▄▖      ▄▖  ▗   "
  printf "  %s\n" "▜▘▌▌▛▘▌▛▌▛▌▌▌▐ ▀▌█▌  ▌ ▀▌▜▘█▌"
  printf "  %s\n" "▐ ▙▌▄▌▌▙▌▌▌▛▌▟▖▙▖▙▖  ▙▌█▌▐▖▙▖"
  printf "\n"
  printf "  %b%s%b\n" "$FAIGATE_UI_BOLD" "$title" "$FAIGATE_UI_RESET"
  if [ -n "$subtitle" ]; then
    printf "  %b%s%b\n" "$FAIGATE_UI_DIM" "$subtitle" "$FAIGATE_UI_RESET"
  fi
  printf "  %s\n\n" "──────────────────────────────────────────────────────────────"
}

faigate_ui_info() {
  printf "  %bℹ%b  %s\n" "$FAIGATE_UI_CYAN" "$FAIGATE_UI_RESET" "$1"
}

faigate_ui_success() {
  printf "  %b✔%b  %s\n" "$FAIGATE_UI_GREEN" "$FAIGATE_UI_RESET" "$1"
}

faigate_ui_warn() {
  printf "  %b!%b  %s\n" "$FAIGATE_UI_YELLOW" "$FAIGATE_UI_RESET" "$1"
}

faigate_ui_error() {
  printf "  %b✖%b  %s\n" "$FAIGATE_UI_RED" "$FAIGATE_UI_RESET" "$1" >&2
}

faigate_ui_pause() {
  printf "\n  Press Enter to continue..."
  read -r _
}

faigate_ui_tip() {
  printf "  %bTip:%b %s\n" "$FAIGATE_UI_CYAN" "$FAIGATE_UI_RESET" "$1"
}

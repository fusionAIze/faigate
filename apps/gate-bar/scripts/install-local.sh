#!/usr/bin/env bash
#
# Local install for Gate Bar — build, wrap, copy, ad-hoc sign.
#
# Why this exists:
#   Gate Bar 0.2+ will ship a notarized .app via Homebrew cask. Until
#   then, developers who want to try it on their own machine can run
#   this script: it builds a release binary, wraps it in a minimal .app
#   bundle, and copies it to ~/Applications/. Because the binary is
#   built and ad-hoc code-signed on the same machine, Gatekeeper trusts
#   it without a full Developer ID notarization round-trip.
#
# Usage:
#   ./scripts/install-local.sh              # build + install + open
#   ./scripts/install-local.sh --no-open    # don't launch after install
#   ./scripts/install-local.sh --uninstall  # remove ~/Applications/Gate Bar.app

set -euo pipefail

APP_NAME="Gate Bar"
APP_BUNDLE_ID="ai.fusionaize.gate-bar"
APP_VERSION="0.1.0"
APP_MIN_MACOS="14.0"
BIN_NAME="GateBar"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="$HOME/Applications"
APP_PATH="$INSTALL_DIR/$APP_NAME.app"

OPEN_AFTER_INSTALL=1
for arg in "$@"; do
  case "$arg" in
    --no-open)
      OPEN_AFTER_INSTALL=0
      ;;
    --uninstall)
      if [[ -d "$APP_PATH" ]]; then
        echo "→ Removing $APP_PATH"
        rm -rf "$APP_PATH"
        echo "✓ Gate Bar uninstalled."
      else
        echo "→ Nothing to uninstall at $APP_PATH"
      fi
      exit 0
      ;;
    -h|--help)
      grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

cd "$PKG_DIR"

# ── 1. Build the release binary ─────────────────────────────────────────────
echo "→ Building $BIN_NAME (release)…"
swift build -c release

BINARY_PATH="$(swift build -c release --show-bin-path)/$BIN_NAME"
if [[ ! -x "$BINARY_PATH" ]]; then
  echo "✗ Release binary not found at $BINARY_PATH" >&2
  exit 1
fi
echo "  built: $BINARY_PATH"

# ── 2. Assemble the .app bundle in a staging dir ────────────────────────────
STAGING="$(mktemp -d -t gatebar-install)"
trap 'rm -rf "$STAGING"' EXIT
BUNDLE="$STAGING/$APP_NAME.app"
mkdir -p "$BUNDLE/Contents/MacOS"

cp "$BINARY_PATH" "$BUNDLE/Contents/MacOS/$BIN_NAME"
chmod +x "$BUNDLE/Contents/MacOS/$BIN_NAME"

cat > "$BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>$APP_BUNDLE_ID</string>
    <key>CFBundleExecutable</key>
    <string>$BIN_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>$APP_VERSION</string>
    <key>CFBundleVersion</key>
    <string>$APP_VERSION</string>
    <key>LSMinimumSystemVersion</key>
    <string>$APP_MIN_MACOS</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticTermination</key>
    <true/>
    <key>NSSupportsSuddenTermination</key>
    <true/>
</dict>
</plist>
PLIST

# PkgInfo — legacy metadata that some macOS versions still sniff. Four
# chars "APPL" + four chars creator code. "????" is the conventional
# placeholder for a no-creator app.
printf 'APPL????' > "$BUNDLE/Contents/PkgInfo"

# ── 3. Ad-hoc code-sign so Gatekeeper trusts the bundle ─────────────────────
# The `-` identity means ad-hoc: no Developer ID, but macOS still records a
# signature that ties the bundle to this machine. First-run Gatekeeper
# prompt may still appear once; after that the app runs freely.
echo "→ Ad-hoc code-signing the bundle…"
codesign --force --deep --sign - "$BUNDLE" 2>&1 | sed 's/^/  /' || {
  echo "✗ codesign failed" >&2
  exit 1
}
# Verify the signature actually took
codesign --verify --verbose=2 "$BUNDLE" 2>&1 | sed 's/^/  /'

# ── 4. Move into place ──────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
if [[ -d "$APP_PATH" ]]; then
  echo "→ Replacing existing $APP_PATH"
  # Kill any running instance so the replace doesn't fail on a busy Mach-O.
  pkill -x "$BIN_NAME" 2>/dev/null || true
  rm -rf "$APP_PATH"
fi
mv "$BUNDLE" "$APP_PATH"
echo "✓ Installed to $APP_PATH"

# ── 5. Hint at launch-at-login (manual — SMAppService needs a code-signed .app
#      with a proper Developer ID; ad-hoc builds can't register. So we print
#      a one-liner the operator can paste to use launchctl instead, which
#      works without Developer ID.) ──────────────────────────────────────────
cat <<EOF

Next steps:
  • Launch now:          open "$APP_PATH"
  • Launch at login:     System Settings → General → Login Items →
                         Open at Login → add "$APP_NAME"
  • Remove later:        $SCRIPT_DIR/install-local.sh --uninstall

Preferences in the popover: gateway URL, Cockpit URL, refresh cadence.
Defaults assume faigate on http://127.0.0.1:4001.
EOF

if (( OPEN_AFTER_INSTALL )); then
  echo "→ Launching Gate Bar…"
  open "$APP_PATH"
fi

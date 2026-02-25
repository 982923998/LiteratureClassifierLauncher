#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="LiteratureClassifierLauncher.app"
DEFAULT_INSTALL_DIR="$HOME/Desktop"
INSTALL_DIR_ARG="${1:-}"
PROJECT_LINK="${LCL_PROJECT_LINK:-$HOME/.literature-classifier-current}"

if [[ "$INSTALL_DIR_ARG" == "-h" || "$INSTALL_DIR_ARG" == "--help" ]]; then
  cat <<'USAGE'
Usage:
  ./web/install_app_to_desktop.sh [INSTALL_DIR]

Arguments:
  INSTALL_DIR    Optional install directory for LiteratureClassifierLauncher.app
                 Default: ~/Desktop

Environment:
  LCL_APP_INSTALL_DIR   Default install directory when INSTALL_DIR is omitted
  LCL_PROJECT_LINK      Symlink path used by the launcher app
USAGE
  exit 0
fi

INSTALL_DIR="${INSTALL_DIR_ARG:-${LCL_APP_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}}"
mkdir -p "$INSTALL_DIR"
DEST_APP="$INSTALL_DIR/$APP_NAME"
TMP_SCRIPT="$(mktemp /tmp/literature-launcher.XXXXXX)"

if ! command -v osacompile >/dev/null 2>&1; then
  echo "osacompile not found. Please ensure AppleScript tools are available on macOS."
  exit 1
fi

# Use an ASCII symlink so Finder-launch environments do not depend on non-ASCII paths.
mkdir -p "$(dirname "$PROJECT_LINK")"
ln -sfn "$PROJECT_ROOT" "$PROJECT_LINK"

PROJECT_LINK_ESCAPED="${PROJECT_LINK//\\/\\\\}"
PROJECT_LINK_ESCAPED="${PROJECT_LINK_ESCAPED//\"/\\\"}"
LAUNCH_SCRIPT="$PROJECT_LINK/web/launch_web_app.sh"
LAUNCH_SCRIPT_ESCAPED="${LAUNCH_SCRIPT//\\/\\\\}"
LAUNCH_SCRIPT_ESCAPED="${LAUNCH_SCRIPT_ESCAPED//\"/\\\"}"

cat >"$TMP_SCRIPT" <<APPLESCRIPT
on run
  set projectLink to "$PROJECT_LINK_ESCAPED"
  set launchScript to "$LAUNCH_SCRIPT_ESCAPED"

  set hasLauncher to do shell script "if [ -x " & quoted form of launchScript & " ]; then echo yes; else echo no; fi"
  if hasLauncher is not "yes" then
    display alert "Literature Classifier" message "未找到启动脚本，请确认项目路径存在并重新运行安装脚本。" as critical
    return
  end if

  do shell script "nohup /bin/zsh " & quoted form of launchScript & " >/dev/null 2>&1 &"
end run
APPLESCRIPT

rm -rf "$DEST_APP"
osacompile -o "$DEST_APP" "$TMP_SCRIPT"
rm -f "$TMP_SCRIPT"

# Remove quarantine if present, so it can be opened without warnings in most cases.
xattr -dr com.apple.quarantine "$DEST_APP" 2>/dev/null || true

echo "Installed: $DEST_APP"
echo "Project link: $PROJECT_LINK -> $PROJECT_ROOT"

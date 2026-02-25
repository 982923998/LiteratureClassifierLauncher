#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_DIR="$HOME/Desktop"
DEST_APP="$DESKTOP_DIR/LiteratureClassifierLauncher.app"
PROJECT_LINK="$HOME/.literature-classifier-current"
TMP_SCRIPT="$(mktemp /tmp/literature-launcher.XXXXXX.applescript)"

if ! command -v osacompile >/dev/null 2>&1; then
  echo "osacompile not found. Please ensure AppleScript tools are available on macOS."
  exit 1
fi

# Use an ASCII symlink so Finder-launch environments do not depend on non-ASCII paths.
ln -sfn "$PROJECT_ROOT" "$PROJECT_LINK"

cat >"$TMP_SCRIPT" <<'APPLESCRIPT'
on run
  set homeDir to POSIX path of (path to home folder)
  set projectLink to homeDir & ".literature-classifier-current"
  set launchScript to projectLink & "/web/launch_web_app.sh"

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

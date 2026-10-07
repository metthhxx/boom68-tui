#!/usr/bin/env bash
#
# Language: Bash
# Filename: uninstall.sh
# Platform: Linux
# Target: Langtu BOOM68 Clean Uninstaller
#

set -e

echo "Удаление софта Langtu BOOM68..."

pkill -f "boom68_" || true

sudo rm -rf /opt/boom68-ctl
sudo rm -f /usr/local/bin/boom68*
sudo rm -f /etc/udev/rules.d/99-langtu-boom68.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

rm -f "${HOME}/.local/share/applications/langtu-boom68.desktop"
rm -f "${HOME}/.config/autostart/langtu-boom68*.desktop"

echo "Софт полностью удален."

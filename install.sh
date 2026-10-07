#!/usr/bin/env bash
#
# Language: Bash
# Filename: install.sh
# Platform: Arch Linux / CachyOS / Manjaro / Fedora / Ubuntu
# Target: Langtu BOOM68 / HE68 Complete Driver & Software Installer (TUI & CLI Suite)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/boom68-ctl"
USER_BIN="/usr/local/bin"

echo "=================================================="
echo "⌨️  Установка софта для клавиатуры Langtu BOOM68  ⌨️"
echo "=================================================="

# 1. Определение дистрибутива и установка зависимостей (без GTK/трея)
echo "[1/4] Проверка зависимостей..."
if command -v pacman &>/dev/null; then
    echo "-> Обнаружен Arch/CachyOS. Ставим зависимости через pacman..."
    sudo pacman -S --needed --noconfirm \
        python \
        python-pillow \
        cava \
        python-numpy \
        pipewire \
        pipewire-pulse
elif command -v apt-get &>/dev/null; then
    echo "-> Обнаружен Debian/Ubuntu. Ставим зависимости через apt..."
    sudo apt-get update
    sudo apt-get install -y \
        python3 \
        python3-pil \
        cava \
        python3-numpy \
        pipewire \
        pipewire-pulse
elif command -v dnf &>/dev/null; then
    echo "-> Обнаружен Fedora. Ставим зависимости через dnf..."
    sudo dnf install -y \
        python3 \
        python3-pillow \
        cava \
        python3-numpy \
        pipewire \
        pipewire-pulseaudio
fi

# 2. Установка udev правил
echo "[2/4] Установка udev-правила доступа к USB..."
sudo cp "${SCRIPT_DIR}/99-langtu-boom68.rules" /etc/udev/rules.d/99-langtu-boom68.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3. Копирование файлов в системную директорию
echo "[3/4] Копирование файлов в ${INSTALL_DIR}..."
sudo mkdir -p "${INSTALL_DIR}"
sudo cp "${SCRIPT_DIR}"/boom68_*.py "${INSTALL_DIR}/"
sudo cp "${SCRIPT_DIR}/99-langtu-boom68.rules" "${INSTALL_DIR}/"
[ -f "${SCRIPT_DIR}/1.jpg" ] && sudo cp "${SCRIPT_DIR}/1.jpg" "${INSTALL_DIR}/"
sudo chmod +x "${INSTALL_DIR}"/*.py

# Создание CLI симлинков в /usr/local/bin
sudo ln -sf "${INSTALL_DIR}/boom68_cli.py" "${USER_BIN}/boom68"
sudo ln -sf "${INSTALL_DIR}/boom68_tui.py" "${USER_BIN}/boom68-tui"
sudo ln -sf "${INSTALL_DIR}/boom68_visualizer.py" "${USER_BIN}/boom68-eq"
sudo ln -sf "${INSTALL_DIR}/boom68_ctl.py" "${USER_BIN}/boom68-ctl"

# 4. Установка ярлыка меню приложений (.desktop)
echo "[4/4] Установка ярлыка TUI в меню приложений..."
DESKTOP_ENTRY_DIR="${HOME}/.local/share/applications"
mkdir -p "${DESKTOP_ENTRY_DIR}"

cat << 'EOF' > "${DESKTOP_ENTRY_DIR}/langtu-boom68.desktop"
[Desktop Entry]
Type=Application
Name=Langtu BOOM68 TUI
Comment=Terminal UI & Hardware Controller for Langtu BOOM68 / HE68
Exec=/usr/local/bin/boom68 tui
Icon=input-keyboard
Terminal=true
Categories=Utility;HardwareSettings;ConsoleOnly;
StartupNotify=false
EOF

chmod +x "${DESKTOP_ENTRY_DIR}/langtu-boom68.desktop"
update-desktop-database "${DESKTOP_ENTRY_DIR}" 2>/dev/null || true

# Удаление старых трей-автостартов если остались
rm -f "${HOME}/.config/autostart/langtu-boom68*.desktop"

echo ""
echo "=================================================="
echo "✅ Установка завершена успешно!"
echo "=================================================="
echo "Как запускать:"
echo "  - Интерактивный TUI: 'boom68' или 'boom68 tui'"
echo "  - Из меню приложений: 'Langtu BOOM68 TUI'"
echo "  - Фоновый эквалайзер: 'boom68 eq start -d'"
echo "  - Консольный статус: 'boom68 status'"
echo "  - Управление подсветкой: 'boom68 set --mode breathing --color \"#e62544\"'"
echo "=================================================="

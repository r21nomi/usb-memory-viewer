#!/bin/bash
# Removes everything install.sh added. Run as the same desktop user.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/usb-viewer}"

pkill -f 'python3 -m usb_viewer' 2>/dev/null || true
rm -f "$HOME/.config/autostart/usb-viewer.desktop"
sudo rm -f /etc/sudoers.d/usb-viewer
sudo rm -f /usr/local/bin/usb-viewer-mount /usr/local/bin/usb-viewer-umount
sudo rm -rf "$INSTALL_DIR"
echo "設定 (~/.config/usb-viewer) とログ (~/.cache/usb-viewer) は残しています。"
echo "ファイルマネージャーの自動マウント設定は ~/.config/pcmanfm/LXDE-pi/pcmanfm.conf で戻せます。"

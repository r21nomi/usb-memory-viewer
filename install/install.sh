#!/bin/bash
# Installs usb-viewer on Raspberry Pi OS (Bookworm or later, desktop edition).
# Run as the desktop user that auto-logs in (usually "pi"), NOT as root:
#   bash install/install.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/usb-viewer}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIOSK_USER="$(id -un)"
CONFIG_DIR="$HOME/.config/usb-viewer"
AUTOSTART_DIR="$HOME/.config/autostart"
PCMANFM_CONF="$HOME/.config/pcmanfm/LXDE-pi/pcmanfm.conf"
PCMANFM_DEFAULT="/etc/xdg/pcmanfm/LXDE-pi/pcmanfm.conf"

say() { printf '\n==> %s\n' "$*"; }

if [[ "$(id -u)" -eq 0 ]]; then
    echo "root ではなく、デスクトップにログインするユーザー（例: pi）で実行してください。" >&2
    exit 1
fi

say "必要なパッケージをインストール (chromium, exfat/ntfs 対応)"
sudo apt-get update
sudo apt-get install -y chromium exfatprogs ntfs-3g 2>/dev/null \
    || sudo apt-get install -y chromium-browser exfatprogs ntfs-3g

say "プログラムを $INSTALL_DIR に配置"
sudo mkdir -p "$INSTALL_DIR"
sudo rsync -a --delete \
    --exclude '.git' --exclude '__pycache__' --exclude '.claude' --exclude 'tests' \
    "$SOURCE_DIR/" "$INSTALL_DIR/"
sudo chown -R root:root "$INSTALL_DIR"
sudo chmod 755 "$INSTALL_DIR/bin/usb-viewer"

say "マウント用ヘルパーを /usr/local/bin に配置"
sudo install -m 0755 -o root -g root "$SOURCE_DIR/install/usb-viewer-mount" /usr/local/bin/usb-viewer-mount
sudo install -m 0755 -o root -g root "$SOURCE_DIR/install/usb-viewer-umount" /usr/local/bin/usb-viewer-umount
sudo mkdir -p /media/usb-viewer

say "sudoers を設定 (ユーザー: $KIOSK_USER がヘルパーのみパスワード無しで実行可)"
sed "s/@USER@/$KIOSK_USER/g" "$SOURCE_DIR/install/sudoers.template" | sudo tee /etc/sudoers.d/usb-viewer >/dev/null
sudo chmod 0440 /etc/sudoers.d/usb-viewer
sudo visudo -cf /etc/sudoers.d/usb-viewer

say "設定ファイルを用意 ($CONFIG_DIR/config.toml)"
mkdir -p "$CONFIG_DIR"
if [[ -f "$CONFIG_DIR/config.toml" ]]; then
    echo "既存の設定ファイルを残します。"
else
    sed "s#/opt/usb-viewer#$INSTALL_DIR#g" "$SOURCE_DIR/config.example.toml" > "$CONFIG_DIR/config.toml"
fi

say "ファイルマネージャーの自動マウントとダイアログを無効化"
mkdir -p "$(dirname "$PCMANFM_CONF")"
if [[ ! -f "$PCMANFM_CONF" && -f "$PCMANFM_DEFAULT" ]]; then
    cp "$PCMANFM_DEFAULT" "$PCMANFM_CONF"
fi
python3 - "$PCMANFM_CONF" <<'PY'
import configparser, sys
from pathlib import Path
path = Path(sys.argv[1])
parser = configparser.ConfigParser(interpolation=None)
parser.optionxform = str
if path.exists():
    parser.read(path, encoding="utf-8")
if not parser.has_section("volume"):
    parser.add_section("volume")
for key in ("mount_on_startup", "mount_removable", "autorun"):
    parser.set("volume", key, "0")
with path.open("w", encoding="utf-8") as handle:
    parser.write(handle, space_around_delimiters=False)
PY

say "デスクトップログイン時の自動起動を登録"
mkdir -p "$AUTOSTART_DIR"
sed "s#@INSTALL_DIR@#$INSTALL_DIR#g" "$SOURCE_DIR/install/usb-viewer.desktop" > "$AUTOSTART_DIR/usb-viewer.desktop"

say "画面のスリープ/ブランクを無効化"
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_blanking 1 || echo "(raspi-config での設定に失敗。手動で無効化してください)"
fi

say "完了"
cat <<EOS
再起動すると自動で起動します:   sudo reboot
今すぐ試す:                     $INSTALL_DIR/bin/usb-viewer
設定:                           $CONFIG_DIR/config.toml
ログ:                           ~/.cache/usb-viewer/usb-viewer.log
EOS

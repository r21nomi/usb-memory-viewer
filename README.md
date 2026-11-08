# usb-viewer

Raspberry Pi 5 に USB メモリを挿すと、その中の HTML 作品を Chromium でフルスクリーン表示する閲覧環境です。
USB メモリそのものを作品として扱うための「再生装置」を想定しています。

## 動作

| 状態 | 表示 |
|---|---|
| USB メモリが挿さっていない | デフォルトの HTML（差し替え可能） |
| USB メモリを挿した | ダイアログなしで、USB 内の HTML をフルスクリーン表示 |
| USB メモリを抜いた | 表示中の HTML を閉じ、デフォルト HTML に戻る |

表示する HTML の選び方（対象フォルダは設定で変更可、既定は USB のルート）:

1. `index.html` があればそれ（大文字小文字は区別しない）
2. なければ、そのフォルダ直下の `.html` / `.htm` のうちアルファベット順で最初のもの
3. HTML が 1 つもなければデフォルト HTML のまま（ログに警告）

USB メモリは「安全な取り外し」なしでそのまま抜けます。読み取り専用でマウントしているので、
抜いても USB 側のデータは壊れません。

## 必要なもの

- Raspberry Pi 5 + Raspberry Pi OS (Bookworm 以降, **デスクトップ版**)
- デスクトップへの自動ログインが有効（Raspberry Pi Imager / `raspi-config` の既定）
- Python 3.11 以上（OS 同梱。追加ライブラリは不要）
- Chromium（インストールスクリプトが入れます）

## インストール

このリポジトリを Pi に置き、デスクトップにログインするユーザー（通常 `pi`）で実行します。

```bash
bash install/install.sh
```

スクリプトがやること:

- `chromium` と exFAT / NTFS 対応パッケージの導入
- プログラム本体を `/opt/usb-viewer` に配置
- マウント用ヘルパー 2 本を `/usr/local/bin` に配置し、`sudoers` でそのヘルパーだけをパスワードなしで許可
- 設定ファイルを `~/.config/usb-viewer/config.toml` に生成（既存ファイルは上書きしない）
- ファイルマネージャー (pcmanfm) の自動マウントと「リムーバブルメディアが挿入されました」ダイアログを無効化
- `~/.config/autostart/usb-viewer.desktop` でデスクトップログイン時に自動起動
- 画面のスリープ/ブランクを無効化

インストール後に再起動すると動き始めます。

```bash
sudo reboot
```

## 設定

`~/.config/usb-viewer/config.toml` を編集します（例は [config.example.toml](config.example.toml)）。

```toml
# USB 内で HTML を探すフォルダ（ルートからの相対パス。"" でルート）
content_dir = ""

# USB が挿さっていないときに表示する HTML。"" で何も表示しない
default_html = "/opt/usb-viewer/default/index.html"

# 抜き差しの確認間隔（秒）
poll_interval_sec = 0.5

[browser]
command = "chromium"
extra_args = []
```

デフォルト画面を差し替えるには `default_html` を自分の HTML のパスに変えるか、
`/opt/usb-viewer/default/index.html` を上書きします。
設定の反映はログアウト→ログイン、または再起動です。

## USB メモリの作り方

- フォーマットは FAT32 / exFAT / NTFS / ext2〜4 のいずれか（FAT32 か exFAT が無難）。それ以外は安全のため拒否します
- ルート（または `content_dir` で指定したフォルダ）に `index.html` を置く
- 画像・JS・CSS などは相対パスで参照すれば一緒に読み込まれます
- `file://` で開くため、`fetch()` でローカルファイルを読む作品は
  `allow_file_access_from_files = true`（既定）が必要です
- USB の外（Pi 側）を指すシンボリックリンクは表示しません

## セキュリティ上の注意

- Raspberry Pi OS の初期ユーザー（`pi` など）は OS 側の設定でパスワードなしの `sudo` が全コマンドに許可されています
  （`/etc/sudoers.d/010_pi-nopasswd`）。本ツールの `sudoers` は 2 つのヘルパーだけを許可しますが、
  初期ユーザーで運用する限りその制限は意味を持ちません。展示で不特定の USB を挿す可能性があるなら、
  専用ユーザーを作って自動ログインさせ、`010_pi-nopasswd` を外した上でそのユーザーでインストールしてください。
- `allow_file_access_from_files = true` のとき、USB 内のページは Pi 上の他のファイルも読めます。
  自分の作品だけを挿す前提なら問題ありませんが、不特定の USB を扱うなら `false` にしてください。
- USB は読み取り専用でマウントします（ext 系はジャーナル再生もしない `noload` 付き）。

## 仕組み

```
usb_viewer/
  devices.py        sysfs (/sys/class/block) を見て USB のパーティションを検出
  mounter.py        sudo 経由でヘルパーを呼び、読み取り専用マウント / 遅延アンマウント
  html_selector.py  index.html 優先、なければアルファベット順で最初の HTML
  browser.py        Chromium を --kiosk で起動 / プロセスグループごと終了
  viewer.py         状態遷移（挿入 → マウント → 表示、抜去 → 閉じる → アンマウント → デフォルト）
  config.py         TOML 設定の読み込みと検証
install/
  usb-viewer-mount   /dev/sdXN だけを /media/usb-viewer/sdXN に ro マウント
  usb-viewer-umount  umount -l（抜かれた後でも後始末できる）
  install.sh         上記のセットアップ一式
```

udev には依存せず、0.5 秒ごとに sysfs をポーリングしています。
デバイスが消えればそのまま「抜かれた」と判断するので、安全な取り外しをしなくても追従します。
挿した直後にマウントが失敗しても数回リトライし、USB から起動している場合はその起動ディスクを対象外にします。
起動時には前回の残骸（残ったマウントや Chromium）を掃除してから始めます。

## 手動で動かす / ログ

```bash
/opt/usb-viewer/bin/usb-viewer
```

```bash
tail -f ~/.cache/usb-viewer/usb-viewer.log
```

停止するには `pkill -f 'python3 -m usb_viewer'`。

## テスト（開発機で実行可、Linux 不要）

```bash
python3 -m unittest discover -s tests -v
```

## トラブルシューティング

- **挿してもダイアログが出る / 勝手にファイルマネージャーが開く**
  `~/.config/pcmanfm/LXDE-pi/pcmanfm.conf` の `[volume]` で
  `mount_removable=0` と `autorun=0` になっているか確認し、再ログインしてください。
- **自動起動しない (Wayland / labwc)**
  Raspberry Pi OS は `~/.config/autostart/*.desktop` を各デスクトップで読みますが、
  動かない場合は `~/.config/labwc/autostart` に
  `/opt/usb-viewer/bin/usb-viewer &` を 1 行追加してください（wayfire なら `~/.config/wayfire.ini` の `[autostart]`）。
- **マウントに失敗する**
  `sudo -n /usr/local/bin/usb-viewer-mount /dev/sda1` を手で実行してエラーを確認。
  `visudo -cf /etc/sudoers.d/usb-viewer` で sudoers が有効か確認できます。
- **マウスカーソルを消したい**
  デフォルト HTML のように作品側で `cursor: none` を指定するのが確実です。
  X11 環境なら `unclutter` も使えます。
- **Chromium が見つからない**
  `config.toml` の `[browser] command` を `chromium-browser` に変えてください。

## アンインストール

```bash
bash install/uninstall.sh
```

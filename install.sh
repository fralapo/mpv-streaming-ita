#!/bin/bash
# Installa la config di mpv, il popup Hyprland e gli script. Scarica anche uosc, thumbfast e ArtCNN
# (non inclusi nel repo). Rilanciabile: sovrascrive i file della repo, non tocca altro.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
mpv_dir=~/.config/mpv
pip_dir=~/.config/mpv-pip

mkdir -p "$mpv_dir"/{scripts,fonts,shaders,script-opts} ~/.local/bin ~/.config/hypr ~/Pictures/mpv

install -m 644 "$here"/mpv/mpv.conf "$here"/mpv/input.conf "$mpv_dir"/
install -m 644 "$here"/mpv/scripts/skip-chapters.lua "$here"/mpv/scripts/flow.lua "$here"/mpv/scripts/gestures.lua "$mpv_dir"/scripts/
install -m 755 "$here"/bin/mpv-pip-toggle ~/.local/bin/
install -m 644 "$here"/hypr/mpv-pip.lua ~/.config/hypr/

# Config del popup per sc_stream (MPV_HOME): include la config principale e attiva il profilo pip
mkdir -p "$pip_dir"
for n in scripts fonts shaders script-opts input.conf; do ln -sfn ../mpv/$n "$pip_dir/$n"; done
printf '%s\n' "include=$mpv_dir/mpv.conf" 'profile=pip' > "$pip_dir/mpv.conf"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "uosc..."
curl -fsSL -o "$tmp/uosc.zip" https://github.com/tomasklaen/uosc/releases/latest/download/uosc.zip
unzip -q -o "$tmp/uosc.zip" -d "$tmp/uosc"
rm -rf "$mpv_dir/scripts/uosc"
cp -r "$tmp/uosc/scripts/uosc" "$mpv_dir/scripts/"
cp "$tmp"/uosc/fonts/* "$mpv_dir/fonts/"
chmod +x "$mpv_dir/scripts/uosc/bin/ziggy-linux"
# Patch: nella barra in alto resta solo il pulsante di chiusura (niente riduci e ingrandisci)
sed -i "s/^\tself.buttons = .*/\tself.buttons = {close}/" "$mpv_dir/scripts/uosc/elements/TopBar.lua"
# Patch: la rotella sul selettore di velocità passa da gestures.lua (passi di 0,1 limitati; su = più lenta, giù = più veloce)
sed -i "s|^function Speed:handle_wheel_up() .*|function Speed:handle_wheel_up() mp.commandv('script-binding', 'gestures/speed-wheel-down') end|; s|^function Speed:handle_wheel_down() .*|function Speed:handle_wheel_down() mp.commandv('script-binding', 'gestures/speed-wheel-up') end|" "$mpv_dir/scripts/uosc/elements/Speed.lua"
mkdir -p "$mpv_dir/script-opts"
cp "$here"/mpv/script-opts/uosc.conf "$here"/mpv/script-opts/flow.conf "$here"/mpv/script-opts/gestures.conf "$mpv_dir/script-opts/"

echo "thumbfast..."
curl -fsSL -o "$mpv_dir/scripts/thumbfast.lua" https://raw.githubusercontent.com/po5/thumbfast/master/thumbfast.lua

echo "ArtCNN..."
art=https://github.com/Artoriuz/ArtCNN/releases/latest/download
for s in ArtCNN_C4F16 ArtCNN_C4F32; do curl -fsSL -o "$mpv_dir/shaders/$s.glsl" "$art/$s.glsl"; done

cat <<EOF

Fatto. Restano due passi a mano:
  1. In ~/.config/hypr/hyprland.lua aggiungi:  require("hypr.mpv-pip")   poi: hyprctl reload
  2. Per il tracciamento e il popup via MCP copia aw-cli-tool/mcp_server.py in ~/.local/share/aw-cli-tool/
     e sc-tool/sc_helper.py in ~/.local/share/sc-tool/, poi riconnetti l'MCP con /mcp.
EOF

#!/bin/bash
# Installa la config di mpv, il popup Hyprland e gli script. Scarica anche uosc, thumbfast e ArtCNN
# (non inclusi nel repo). Rilanciabile: sovrascrive i file della repo, non tocca altro.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
mpv_dir=~/.config/mpv
pip_dir=~/.config/mpv-pip

mkdir -p "$mpv_dir"/{scripts,fonts,shaders,script-opts} ~/.local/bin ~/.config/hypr ~/Pictures/mpv

install -m 644 "$here"/mpv/mpv.conf "$here"/mpv/input.conf "$mpv_dir"/
install -m 644 "$here"/mpv/scripts/skip-chapters.lua "$here"/mpv/scripts/flow.lua "$here"/mpv/scripts/gestures.lua "$here"/mpv/scripts/hls-subs.lua "$here"/mpv/scripts/progress.lua "$here"/mpv/scripts/quality.lua "$mpv_dir"/scripts/
install -m 755 "$here"/bin/mpv-pip-toggle "$here"/bin/mpv-theme "$here"/bin/mpv-streaming-update ~/.local/bin/
# mpv-streaming-update aggiorna da qui: si ricorda dove sta il repo
mkdir -p ~/.local/state/mpv-streaming-ita
echo "$here" > ~/.local/state/mpv-streaming-ita/repo
mkdir -p "$mpv_dir/themes"
install -m 644 "$here"/themes/*.conf "$mpv_dir/themes/"
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
# Le modifiche si applicano sulla copia scaricata: se la nuova versione non le accetta resta quella già installata
problems=0 patched=1
"$here"/tools/patch-uosc.sh "$tmp/uosc/scripts/uosc" || { patched=0; problems=1; }
if (( patched )) || [[ ! -d $mpv_dir/scripts/uosc ]]; then
    rm -rf "$mpv_dir/scripts/uosc"
    cp -r "$tmp/uosc/scripts/uosc" "$mpv_dir/scripts/"
    cp "$tmp"/uosc/fonts/* "$mpv_dir/fonts/"
    chmod +x "$mpv_dir/scripts/uosc/bin/ziggy-linux"
else
    echo "uosc: tengo la versione già installata finché le modifiche non vengono aggiornate nel repo" >&2
fi
mkdir -p "$mpv_dir/script-opts"
cp "$here"/mpv/script-opts/uosc.conf "$here"/mpv/script-opts/flow.conf "$here"/mpv/script-opts/gestures.conf "$mpv_dir/script-opts/"
# Tema: THEME=nord ./install.sh per sceglierlo, altrimenti resta quello già in uso (o lo standard)
~/.local/bin/mpv-theme "${THEME:-$(cat "$mpv_dir/themes/current" 2>/dev/null || echo standard)}"

echo "thumbfast..."
curl -fsSL -o "$mpv_dir/scripts/thumbfast.lua" https://raw.githubusercontent.com/po5/thumbfast/master/thumbfast.lua

echo "ArtCNN..."
art=https://github.com/Artoriuz/ArtCNN/releases/latest/download
for s in ArtCNN_C4F16 ArtCNN_C4F32; do curl -fsSL -o "$mpv_dir/shaders/$s.glsl" "$art/$s.glsl"; done

# Server MCP, helper StreamingCommunity e skill per gli agenti AI (servono solo per riprodurre chiedendolo a un agente).
# ~/.agents/skills è la cartella comune (Codex, Gemini CLI, OpenCode...); Claude Code legge solo ~/.claude/skills
mkdir -p ~/.local/share/aw-cli-tool ~/.local/share/sc-tool/run ~/.agents/skills/aw-cli ~/.claude/skills/aw-cli
install -m 644 "$here"/aw-cli-tool/mcp_server.py ~/.local/share/aw-cli-tool/
install -m 644 "$here"/sc-tool/sc_helper.py ~/.local/share/sc-tool/
install -m 644 "$here"/skill/aw-cli/SKILL.md ~/.agents/skills/aw-cli/
install -m 644 "$here"/skill/aw-cli/SKILL.md ~/.claude/skills/aw-cli/

# Lanciato da mpv-streaming-update: il riepilogo lo fa lui
[[ -n ${MPV_STREAMING_UPDATE:-} ]] && exit $problems

cat <<EOF

Fatto. Passi rimanenti (dettagli nel README):
  1. Solo con Hyprland: in ~/.config/hypr/hyprland.lua aggiungi  require("hypr.mpv-pip")  poi  hyprctl reload
  2. Solo per gli agenti AI: installa aw-cli e StreamingCommunity, poi registra il server MCP nel tuo agente,
     per esempio in Claude Code:
       claude mcp add aw-cli -- ~/.local/share/uv/tools/aw-cli/bin/python ~/.local/share/aw-cli-tool/mcp_server.py
     (comandi per Codex, Gemini CLI, OpenCode e gli altri nel README)
  3. Aggiornamenti: mpv-streaming-update aggiorna tutto e controlla che funzioni;
     mpv-streaming-update --auto-on lo fa da solo ogni settimana.
EOF
exit $problems

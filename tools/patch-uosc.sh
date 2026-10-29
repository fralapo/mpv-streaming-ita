#!/bin/bash
# Applica le modifiche a uosc e controlla che siano andate a segno.
# sed non segnala nulla se la riga cercata non esiste più: se una nuova versione di uosc la cambia,
# qui si fallisce con un messaggio chiaro invece di installare un uosc senza modifiche.
# Uso: patch-uosc.sh <cartella scripts/uosc>
set -euo pipefail

dir=${1:?uso: patch-uosc.sh <cartella scripts/uosc>}
top=$dir/elements/TopBar.lua
speed=$dir/elements/Speed.lua
fail=0

# Nella barra in alto resta solo il pulsante di chiusura (niente riduci e ingrandisci)
sed -i "s/^\tself.buttons = .*/\tself.buttons = {close}/" "$top"
grep -q $'^\tself.buttons = {close}$' "$top" || { echo "uosc: TopBar.lua è cambiato, modifica della barra in alto non applicata" >&2; fail=1; }

# La rotella sul selettore di velocità passa da gestures.lua (passi di 0,1 limitati; su = più lenta, giù = più veloce)
sed -i "s|^function Speed:handle_wheel_up() .*|function Speed:handle_wheel_up() mp.commandv('script-binding', 'gestures/speed-wheel-down') end|; s|^function Speed:handle_wheel_down() .*|function Speed:handle_wheel_down() mp.commandv('script-binding', 'gestures/speed-wheel-up') end|" "$speed"
[[ $(grep -c "gestures/speed-wheel-" "$speed") -eq 2 ]] || { echo "uosc: Speed.lua è cambiato, modifica della rotella sulla velocità non applicata" >&2; fail=1; }

exit $fail

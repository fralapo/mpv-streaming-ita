# media-player-setup

Setup personale per guardare anime, serie e film con mpv su Hyprland (Omarchy), pilotato da Claude Code
tramite un server MCP per aw-cli e StreamingCommunity.

## Contenuto

| Percorso | Cosa fa |
| --- | --- |
| `mpv/mpv.conf`, `mpv/input.conf` | gpu-next su Vulkan, decodifica VA-API (Intel Arc), shader ArtCNN, audio giapponese e sottotitoli italiani, profilo `[pip]` |
| `mpv/scripts/skip-chapters.lua` | TAB salta i capitoli Opening, Ending e Recap; `auto=yes` in `script-opts/skip-chapters.conf` per saltarli da solo |
| `mpv-pip/mpv.conf` | config alternativa (via `MPV_HOME`) per aprire anche `sc_stream` in popup |
| `hypr/mpv-pip.lua` | regole Hyprland: finestra `AnimePip` fluttuante, fissata su tutti i desktop, 16:9, in basso a destra |
| `bin/mpv-pip-toggle` | alterna una finestra mpv tra schermo intero e popup (tasto `P` in mpv, `SUPER+CTRL+P`); ignora le finestre che non sono mpv |
| `aw-cli-tool/mcp_server.py` | server MCP per aw-cli: capitoli AniSkip, tracciamento preciso via IPC di mpv, parametro `popup` |
| `sc-tool/sc_helper.py` | helper per StreamingCommunity usato dall'MCP |
| `claude-skill/aw-cli/SKILL.md` | skill di Claude Code per riprodurre e tracciare |

uosc, thumbfast e gli shader ArtCNN non sono nel repo: li scarica `install.sh`.

## Installazione

```
./install.sh
```

Poi aggiungi `require("hypr.mpv-pip")` a `~/.config/hypr/hyprland.lua` ed esegui `hyprctl reload`.

## Popup

- Si sposta con `SUPER` + trascina (tasto sinistro) e si ridimensiona con `SUPER` + tasto destro.
- L'app-id `AnimePip` non deve contenere "mpv", altrimenti le regole di Omarchy lo centrano a 875x600.
- Lo script di toggle agisce solo su finestre `mpv` o `AnimePip`, perché le finestre vere dell'utente non vanno toccate.

## Note

- La prima apertura compila la pipeline di ArtCNN (circa 35 secondi, una volta per formato video, poi è in cache).
- I token AniList e Simkl stanno nella config di aw-cli e non sono in questo repo.

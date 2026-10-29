# media-player-setup

Setup personale per guardare anime, serie e film con mpv su Hyprland (Omarchy), pilotato da Claude Code
tramite un server MCP per aw-cli e StreamingCommunity.

## Contenuto

| Percorso | Cosa fa |
| --- | --- |
| `mpv/mpv.conf`, `mpv/input.conf` | gpu-next su Vulkan, decodifica VA-API (Intel Arc), shader ArtCNN, audio giapponese e sottotitoli italiani, profilo `[pip]` |
| `mpv/scripts/skip-chapters.lua` | TAB salta Opening, Ending e Recap; compare un pulsante «Salta» nella barra solo dentro questi segmenti; `A` attiva il salto automatico |
| `mpv/scripts/flow.lua`, `mpv/script-opts/flow.conf` | avviso «Ripreso da …» e, a fine episodio, chiusura dopo 8 secondi annullabile con ESC |
| `mpv/scripts/gestures.lua`, `mpv/script-opts/gestures.conf` | velocità a passi di 0,1, tieni premuto per 2×, clic/doppio clic/trascina sul video, indicatore di velocità |
| `mpv/scripts/hls-subs.lua` | carica come file esterno i sottotitoli italiani degli stream HLS a segmento unico (StreamingCommunity), così le battute non si ripetono |
| `mpv/scripts/progress.lua` | per StreamingCommunity: salva il minuto ogni 15 s e alla chiusura, riparte da lì; il server MCP segna su Simkl solo oltre il 90% |
| `mpv/scripts/quality.lua` | qualità degli stream HLS: automatica (non oltre ciò che la finestra mostra, scende se il buffer si svuota, risale con rete buona), a mano con Q o il pulsante HD |
| `mpv/script-opts/uosc.conf` | barra del tempo, controlli, palette e segmenti OP/ED evidenziati sulla timeline |
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

## Scorciatoie

`?` apre l'elenco completo con ricerca; tasto destro o Invio apre il menu in italiano.

| Tasto / gesto | Azione |
| --- | --- |
| Spazio o clic rapido sul video | pausa (nel popup una presa più lunga di 0,25 s è uno spostamento, non una pausa) |
| Q o pulsante HD nella barra | qualità video: automatica (default) o 1080p / 720p / 480p a scelta |
| ← → / Maiusc + ← → | ±5 s / ±30 s |
| tieni premuto → (o il clic, a schermo intero) | 2× finché tieni, poi torna com'era (anche da pausa) |
| `d` / `s` / `r` | velocità +0,1 / −0,1 / torna a 1× (da 0,1× a 4×); anche `]` `+` `[` `-`, e pulsanti − e + accanto al selettore |
| 0 … 9 | salta a 0 … 90% |
| Ctrl + ← → | riga di sottotitoli precedente / successiva |
| ↑ ↓ o rotella | volume; scorrimento orizzontale = ±5 s per gesto; Maiusc + rotella = ±10 s |
| rotella sul selettore di velocità | su = più lenta, giù = più veloce, 0,1 per scatto e al massimo ~8 scatti al secondo |
| clic centrale | muto |
| `p` o doppio clic | popup ↔ schermo intero |
| trascina il video | sposta la finestra (nel popup) |
| `f` | schermo intero |
| TAB / `A` | salta OP/ED / salto automatico on-off |
| `v`, `j`, `z` `x` | sottotitoli: mostra, traccia, ritardo |
| `n` | volume uniforme (dialoghi e scene forti) |
| Ctrl+a, Ctrl+d, Ctrl+i | upscaling ArtCNN, deband, interpolazione |
| Ctrl+s / Ctrl+Maiusc+s | screenshot con / senza sottotitoli |
| `<` `>` | episodio precedente / successivo |

## Popup

- Si sposta con `SUPER` + trascina (tasto sinistro) e si ridimensiona con `SUPER` + tasto destro.
- L'app-id `AnimePip` non deve contenere "mpv", altrimenti le regole di Omarchy lo centrano a 875x600.
- Lo script di toggle agisce solo su finestre `mpv` o `AnimePip`, perché le finestre vere dell'utente non vanno toccate.

## Note

- La prima apertura compila la pipeline di ArtCNN (circa 35 secondi, una volta per formato video, poi è in cache).
- I token AniList e Simkl stanno nella config di aw-cli e non sono in questo repo.

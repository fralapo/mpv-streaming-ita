<a id="readme-top"></a>

# mpv-streaming-ita

**Configurazione di [mpv](https://mpv.io) per guardare anime, serie TV e film in italiano su Linux, con salto di opening ed ending, popup sempre in primo piano e un server MCP per avviarli chiedendolo a un agente AI (Claude Code, Codex, Gemini CLI, OpenCode...).**

[![Compatibilità con i progetti esterni](https://github.com/fralapo/mpv-streaming-ita/actions/workflows/upstream-check.yml/badge.svg)](https://github.com/fralapo/mpv-streaming-ita/actions/workflows/upstream-check.yml)
[![Licenza MIT](https://img.shields.io/badge/licenza-MIT-blue)](LICENSE)
[![testato con mpv 0.41](https://img.shields.io/badge/mpv-0.41-691f69)](https://mpv.io)
[![Linux Wayland](https://img.shields.io/badge/Linux-Wayland-333)](#requisiti)
[![Hyprland opzionale](https://img.shields.io/badge/Hyprland-opzionale-58e1ff)](https://github.com/hyprwm/Hyprland)
[![Server MCP per agenti AI](https://img.shields.io/badge/MCP-agenti%20AI-d97757)](#agenti-ai-e-server-mcp)

mpv-streaming-ita è un insieme di file di configurazione e script Lua per mpv, più un server MCP in Python. Lo uso ogni giorno su un portatile con Omarchy (Arch + Hyprland) per guardare gli anime da AnimeWorld e AnimeUnity tramite [aw-cli](https://github.com/fexh10/aw-cli), e i film e le serie da StreamingCommunity tramite [StreamingCommunity-downloader-streamer](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer). La parte su mpv funziona da sola con qualsiasi video. Hyprland e gli agenti AI sono facoltativi.

Il repo non contiene video, link a contenuti né account: si limita a configurare il player e a collegare strumenti open source esistenti.

## Indice

- [Cosa fa](#cosa-fa)
- [Requisiti](#requisiti)
- [Installazione](#installazione)
- [Aggiornamenti](#aggiornamenti)
- [Agenti AI e server MCP](#agenti-ai-e-server-mcp)
- [Contenuto del repo](#contenuto-del-repo)
- [Temi](#temi)
- [Scorciatoie](#scorciatoie)
- [Popup](#popup)
- [Domande frequenti](#domande-frequenti)
- [Progetti usati](#progetti-usati)
- [Licenza](#licenza)

## Cosa fa

- **Salta opening, ending e recap.** I capitoli arrivano da [AniSkip](https://github.com/aniskip/aniskip-api). Mentre sei dentro uno di questi segmenti compare il pulsante «Salta», TAB salta subito e `A` attiva il salto automatico.
- **Riprende da dove eri rimasto**, anche per gli stream di StreamingCommunity. La posizione viene salvata ogni 15 secondi e alla chiusura, e l'episodio viene segnato come visto su AniList o Simkl solo oltre il 90%.
- **Qualità automatica per gli stream HLS.** Non supera la risoluzione che la finestra può mostrare, scende se il buffer si svuota e risale quando la rete regge. Q o il pulsante HD la fissano a mano.
- **Sottotitoli italiani senza righe ripetute** per gli stream HLS a segmento unico di StreamingCommunity.
- **Popup** in basso a destra, fissato su tutti i desktop, con controlli ridotti e sottotitoli 2,1 volte più grandi. Ci si passa con `P` o con un doppio clic.
- **Gesti e velocità.** La velocità va a passi di 0,1, tenendo premuto → o il clic si va a 2× finché tieni, e c'è un indicatore della velocità attuale.
- **Upscaling ArtCNN** sugli anime: [ArtCNN](https://github.com/Artoriuz/ArtCNN) è addestrato sull'animazione e si attiva solo con il profilo `anime`.
- **Bande nere vere** attorno al video: su uno schermo OLED quei pixel restano spenti.
- **Sette temi di colore** per l'interfaccia, da cambiare con un comando.
- Interfaccia [uosc](https://github.com/tomasklaen/uosc) in italiano, con anteprime sulla timeline grazie a [thumbfast](https://github.com/po5/thumbfast).

## Requisiti

| Cosa | Serve per | Note |
| --- | --- | --- |
| Linux con Wayland | tutto | testato su Arch (Omarchy). Su X11 togli `gpu-context=waylandvk` da `mpv.conf` |
| mpv recente, `curl`, `unzip` | tutto | testato con mpv 0.41 |
| Font Noto Sans | sottotitoli e interfaccia | su Arch è il pacchetto `noto-fonts` |
| GPU con Vulkan e VA-API | decodifica hardware e ArtCNN | configurato per Intel Arc; con altre GPU di solito basta lasciare `hwdec=vaapi,auto-safe` |
| [Hyprland](https://github.com/hyprwm/Hyprland) con config in Lua, `jq` | popup e `SUPER+CTRL+P` | senza Hyprland il resto funziona, il popup no |
| [mpv-mpris](https://github.com/hoyon/mpv-mpris) | tasti multimediali da qualsiasi finestra | facoltativo |
| [aw-cli](https://github.com/fexh10/aw-cli), [StreamingCommunity](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer), un agente con supporto MCP | riprodurre chiedendolo a un agente AI | facoltativi, vedi [sotto](#agenti-ai-e-server-mcp) |

## Installazione

```bash
git clone https://github.com/fralapo/mpv-streaming-ita.git
cd mpv-streaming-ita
./install.sh
```

`install.sh` copia la configurazione in `~/.config/mpv`, gli script in `~/.local/bin` e scarica uosc, thumbfast e gli shader ArtCNN, che non sono inclusi nel repo. Puoi rilanciarlo quando vuoi: sovrascrive solo i file che installa lui e mantiene il tema scelto. Per aggiornare c'è [`mpv-streaming-update`](#aggiornamenti).

Attenzione: se hai già un `mpv.conf` o un `input.conf`, verranno sostituiti. Fanne una copia prima.

Con Hyprland, aggiungi questa riga a `~/.config/hypr/hyprland.lua` e ricarica:

```lua
require("hypr.mpv-pip")
```

```bash
hyprctl reload
```

Al primo avvio ArtCNN compila la sua pipeline. Ci vogliono circa 35 secondi, una volta per formato video, poi resta in cache.

<p align="right">(<a href="#readme-top">torna su</a>)</p>

## Aggiornamenti

uosc, thumbfast, ArtCNN, aw-cli e StreamingCommunity cambiano per conto loro. Per seguirli:

```bash
mpv-streaming-update
```

Il comando scarica le novità del repo, reinstalla la configurazione con le ultime versioni di uosc, thumbfast e ArtCNN e porta aw-cli e StreamingCommunity all'ultima versione su PyPI. Poi controlla che tutto funzioni ancora:

- se una nuova versione di uosc non accetta più le modifiche di questo repo, resta installata quella di prima;
- se una nuova versione di aw-cli o StreamingCommunity impedisce al server MCP di partire, torna alla versione precedente e salta quella rotta finché non ne esce un'altra;
- configurazione, token e cronologia di aw-cli vengono salvati prima e rimessi a posto dopo, perché aw-cli li tiene dentro la cartella del pacchetto e una reinstallazione li cancellerebbe.

Per farlo andare da solo:

```bash
mpv-streaming-update --auto-on
```

Un timer di systemd lo lancia ogni giorno, ma l'aggiornamento parte solo se sono passati 6 giorni dall'ultimo riuscito e mpv non è aperto. Se qualcosa va storto arriva una notifica sul desktop; il resto finisce in `~/.local/state/mpv-streaming-ita/update.log`. `--auto-off` lo disattiva.

Ogni lunedì GitHub prova il repo con le ultime versioni di uosc, aw-cli e StreamingCommunity ([risultati](https://github.com/fralapo/mpv-streaming-ita/actions/workflows/upstream-check.yml)). Se un progetto esterno cambia in modo incompatibile, lo si vede lì prima che arrivi sul tuo computer.

## Agenti AI e server MCP

Questa parte è facoltativa. Il server MCP in `aw-cli-tool/mcp_server.py` espone aw-cli e StreamingCommunity come strumenti per qualsiasi agente che supporti il [Model Context Protocol](https://modelcontextprotocol.io): Claude Code, Codex, Gemini CLI, OpenCode, Cursor e altri. Puoi quindi scrivere «riproduci l'episodio 5 di Frieren» o «continua The Last of Us», e l'agente cerca il titolo, apre mpv e tiene traccia di dove sei arrivato.

La skill in `skill/aw-cli/SKILL.md` segue il formato aperto [Agent Skills](https://agentskills.io) e spiega all'agente quale strumento usare e quando. `install.sh` la copia in `~/.agents/skills/`, la cartella letta da Codex, Gemini CLI e OpenCode, e in `~/.claude/skills/` per Claude Code.

**1. Installa aw-cli** con [uv](https://docs.astral.sh/uv/). Il server MCP gira con il Python di questo ambiente:

```bash
uv tool install aw-cli
```

**2. Installa StreamingCommunity** in un ambiente separato, per film e serie TV:

```bash
python -m venv ~/.local/share/sc-tool/venv
~/.local/share/sc-tool/venv/bin/pip install streamingcommunity-download-stream
```

**3. Registra il server MCP** nel tuo agente. `install.sh` ha già copiato server, helper e skill. Il server si avvia sempre con lo stesso comando:

```bash
~/.local/share/uv/tools/aw-cli/bin/python ~/.local/share/aw-cli-tool/mcp_server.py
```

Claude Code:

```bash
claude mcp add aw-cli -- ~/.local/share/uv/tools/aw-cli/bin/python ~/.local/share/aw-cli-tool/mcp_server.py
```

Codex:

```bash
codex mcp add aw-cli -- ~/.local/share/uv/tools/aw-cli/bin/python ~/.local/share/aw-cli-tool/mcp_server.py
```

Gemini CLI:

```bash
gemini mcp add -s user aw-cli ~/.local/share/uv/tools/aw-cli/bin/python ~/.local/share/aw-cli-tool/mcp_server.py
```

<details>
<summary>OpenCode, Cursor e altri client con configurazione JSON</summary>

Nei file JSON `~` non viene espanso: sostituisci `/home/TUONOME` con il percorso della tua home (`echo $HOME`).

OpenCode, in `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "aw-cli": {
      "type": "local",
      "command": ["/home/TUONOME/.local/share/uv/tools/aw-cli/bin/python", "/home/TUONOME/.local/share/aw-cli-tool/mcp_server.py"]
    }
  }
}
```

Cursor (`~/.cursor/mcp.json`) e la maggior parte degli altri client:

```json
{
  "mcpServers": {
    "aw-cli": {
      "command": "/home/TUONOME/.local/share/uv/tools/aw-cli/bin/python",
      "args": ["/home/TUONOME/.local/share/aw-cli-tool/mcp_server.py"]
    }
  }
}
```

Se il tuo agente non legge `~/.agents/skills/`, copia `skill/aw-cli/SKILL.md` nella sua cartella delle skill o incollane il contenuto nelle sue istruzioni.

</details>

**4. Collega le liste**, se le usi. Basta chiederlo all'agente:

- **AniList:** genera un token su [anilist.co](https://anilist.co/settings/developer) e chiedi «imposta il token AniList …» (strumento `config_set`, chiave `anilist.token`).
- **Simkl:** crea un'app su [simkl.com/settings/developer](https://simkl.com/settings/developer/) con redirect `http://localhost:9876/callback`. Imposta poi `simkl.client_id` e `simkl.client_secret` con `config_set` e lancia `simkl_auth`, che apre il browser per il login.

I token restano nella configurazione di aw-cli sul tuo computer. Il repo non li contiene e `config_get` li mostra oscurati.

<details>
<summary>Strumenti MCP disponibili</summary>

| Strumento | Cosa fa |
| --- | --- |
| `watch` | sceglie da solo la fonte: anime con aw-cli, film e serie con StreamingCommunity |
| `search`, `info`, `episodes`, `latest` | ricerca e dettagli degli anime |
| `play` | riproduce un anime; senza episodio riparte dal successivo all'ultimo visto |
| `download`, `offline` | scarica in `~/Videos/Anime` ed elenca gli episodi scaricati |
| `sc_search`, `sc_episodes`, `sc_sites` | ricerca di film e serie su StreamingCommunity |
| `sc_stream`, `sc_download`, `sc_status` | riproduce o scarica film ed episodi e ne segue l'avanzamento |
| `watchlist` | vista unica di AniList, Simkl, cronologia aw-cli e StreamingCommunity |
| `anilist_list`, `simkl_list`, `simkl_mark`, `simkl_auth` | liste e sincronizzazione |
| `history`, `sc_history`, `history_remove` | cronologia |
| `config_get`, `config_set` | configurazione di aw-cli, AniList e Simkl |

</details>

Dopo aver modificato `mcp_server.py` riavvia il server dal tuo agente (in Claude Code con `/mcp`).

<p align="right">(<a href="#readme-top">torna su</a>)</p>

## Contenuto del repo

| Percorso | Cosa fa |
| --- | --- |
| `mpv/mpv.conf`, `mpv/input.conf` | gpu-next su Vulkan, decodifica VA-API, audio giapponese e sottotitoli italiani, profili `anime` e `pip` |
| `mpv/scripts/skip-chapters.lua` | TAB salta opening, ending e recap; il pulsante «Salta» compare solo dentro questi segmenti; `A` attiva il salto automatico |
| `mpv/scripts/flow.lua`, `mpv/script-opts/flow.conf` | avviso «Ripreso da …» e, a fine episodio, chiusura dopo 8 secondi (ESC la annulla) |
| `mpv/scripts/gestures.lua`, `mpv/script-opts/gestures.conf` | velocità a passi di 0,1, 2× tenendo premuto, clic, doppio clic e trascinamento sul video, indicatore di velocità, modalità popup |
| `mpv/scripts/hls-subs.lua` | carica i sottotitoli italiani degli stream HLS a segmento unico come file esterno, così le battute non si ripetono |
| `mpv/scripts/progress.lua` | per StreamingCommunity: salva la posizione ogni 15 s e alla chiusura, e riparte da lì |
| `mpv/scripts/quality.lua` | qualità degli stream HLS, automatica o scelta a mano |
| `mpv/script-opts/uosc.conf` | barra del tempo, controlli e segmenti OP/ED evidenziati sulla timeline |
| `mpv-pip/mpv.conf` | configurazione alternativa (via `MPV_HOME`) per aprire gli stream direttamente nel popup |
| `hypr/mpv-pip.lua` | regole Hyprland per il popup `AnimePip`: fluttuante, su tutti i desktop, 16:9, in basso a destra |
| `bin/mpv-pip-toggle` | alterna la finestra di mpv tra schermo intero e popup e ignora le finestre che non sono mpv |
| `bin/mpv-theme`, `themes/*.conf` | temi di colore e il comando per cambiarli |
| `bin/mpv-streaming-update` | aggiorna tutto, controlla che funzioni e torna indietro se qualcosa si rompe |
| `tools/patch-uosc.sh`, `tools/check-mcp.py` | applicano e verificano le modifiche a uosc; provano il server MCP come farebbe un agente |
| `.github/workflows/upstream-check.yml` | prova settimanale con le ultime versioni dei progetti esterni |
| `aw-cli-tool/mcp_server.py` | server MCP: aw-cli, StreamingCommunity, capitoli AniSkip, tracciamento della posizione via IPC di mpv, AniList e Simkl |
| `sc-tool/sc_helper.py` | helper che il server MCP usa per StreamingCommunity |
| `skill/aw-cli/SKILL.md` | skill nel formato Agent Skills: spiega a qualsiasi agente come usare gli strumenti |

## Temi

Il tema predefinito è `standard`, bianco su nero. Per sceglierne un altro:

```bash
mpv-theme
```

```bash
mpv-theme tokyo-night
```

Il primo comando mostra l'elenco (l'asterisco indica il tema attivo). Il secondo applica il tema dalla prossima apertura di mpv. Puoi sceglierlo anche in fase di installazione con `THEME=nord ./install.sh`.

| Tema | Aspetto |
| --- | --- |
| `standard` | bianco su nero |
| `catppuccin` | viola chiaro su blu notte |
| `tokyo-night` | blu elettrico su blu scuro |
| `nord` | azzurro ghiaccio su grigio ardesia |
| `gruvbox` | giallo caldo su marrone scuro |
| `rose-pine` | rosa antico su viola notte |
| `dracula` | viola acceso su grigio scuro |

Per crearne uno nuovo, copia un file di `~/.config/mpv/themes/` con un altro nome e cambia i colori (formato RRGGBB).

## Scorciatoie

`?` apre l'elenco completo con ricerca. Il tasto destro o Invio aprono il menu.

| Tasto o gesto | Azione |
| --- | --- |
| Spazio o clic rapido sul video | pausa |
| Q o pulsante HD | qualità: automatica, oppure 1080p, 720p o 480p |
| ← → / Maiusc + ← → | ±5 s / ±30 s |
| tieni premuto → (o il clic, a schermo intero) | 2× finché tieni premuto, poi torna com'era (anche da pausa) |
| `d` / `s` / `r` | velocità +0,1 / −0,1 / di nuovo 1× (da 0,1× a 4×) |
| 0 … 9 | salta a 0 … 90% |
| Ctrl + ← → | riga di sottotitoli precedente / successiva |
| ↑ ↓ o rotella | volume; scorrimento orizzontale = ±5 s, Maiusc + rotella = ±10 s |
| rotella sul selettore di velocità | su = più lenta, giù = più veloce |
| clic centrale | muto |
| `p` o doppio clic | popup ↔ schermo intero |
| trascina il video | sposta la finestra (nel popup) |
| `f` | schermo intero |
| TAB / `A` | salta OP/ED / salto automatico sì-no |
| `v`, `j`, `z` `x` | sottotitoli: mostra, cambia traccia, ritardo |
| `n` | volume uniforme tra dialoghi e scene rumorose |
| Ctrl+a, Ctrl+d, Ctrl+i | ArtCNN, deband, interpolazione |
| Ctrl+s / Ctrl+Maiusc+s | screenshot con / senza sottotitoli (in `~/Pictures/mpv`) |
| `<` `>` | episodio precedente / successivo |

## Popup

Quando la finestra è più bassa di metà schermo, `gestures.lua` passa alla modalità popup:

- la barra si riduce a sottotitoli, salto OP/ED, −10 s, pausa, +10 s e «torna a schermo intero», e il resto resta nel menu del tasto destro;
- i sottotitoli diventano 2,1 volte più grandi (`popup_sub_scale` in `gestures.conf`) e l'interfaccia si compatta;
- clic = pausa, doppio clic = schermo intero, trascina = sposta, rotella = volume;
- con Hyprland si sposta anche con `SUPER` + trascinamento e si ridimensiona con `SUPER` + tasto destro.

L'app-id del popup è `AnimePip` e non contiene «mpv» apposta: altrimenti le regole di Omarchy lo centrerebbero a 875×600.

<p align="right">(<a href="#readme-top">torna su</a>)</p>

## Domande frequenti

**Funziona senza Hyprland?**
Sì. Configurazione, script, temi e server MCP funzionano con qualsiasi compositor Wayland. Solo il popup fissato in basso a destra e `SUPER+CTRL+P` richiedono Hyprland.

**Funziona su X11, macOS o Windows?**
Su X11 sì, dopo aver tolto `gpu-context=waylandvk` da `mpv.conf`. Su macOS e Windows non l'ho provato: gli script Lua dovrebbero andare, ma `install.sh`, il popup e i percorsi sono pensati per Linux.

**Serve un agente AI per usarlo?**
No. Il server MCP è un'aggiunta. Puoi usare mpv con aw-cli dal terminale, oppure aprire qualsiasi file o URL.

**Dove finiscono i miei token di AniList e Simkl?**
Nella configurazione di aw-cli sul tuo computer, mai nel repo.

**Perché i sottotitoli degli stream si ripetevano?**
Alcuni stream HLS hanno tutti i sottotitoli in un unico segmento, e mpv mostrava le stesse battute più volte. `hls-subs.lua` carica quel segmento come file di sottotitoli esterno.

## Progetti usati

Questo repo configura e collega il lavoro di altri:

- [mpv](https://mpv.io): il player
- [uosc](https://github.com/tomasklaen/uosc): interfaccia, barra e menu
- [thumbfast](https://github.com/po5/thumbfast): anteprime sulla timeline
- [ArtCNN](https://github.com/Artoriuz/ArtCNN): upscaling per l'animazione
- [AniSkip](https://github.com/aniskip/aniskip-api): tempi di opening ed ending
- [mpv-mpris](https://github.com/hoyon/mpv-mpris): tasti multimediali e controllo dal sistema
- [aw-cli](https://github.com/fexh10/aw-cli): anime da AnimeWorld e AnimeUnity
- [StreamingCommunity-downloader-streamer](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer): film e serie TV
- [AniList](https://anilist.co), [Simkl](https://simkl.com) e [MAL-Sync](https://github.com/MALSync/MALSync): liste e sincronizzazione
- [Hyprland](https://github.com/hyprwm/Hyprland) e [Omarchy](https://github.com/basecamp/omarchy): il desktop su cui è nato
- il [Model Context Protocol](https://modelcontextprotocol.io) e il formato [Agent Skills](https://agentskills.io)

## Licenza

[MIT](LICENSE). uosc, thumbfast, ArtCNN e gli altri progetti hanno le loro licenze; `install.sh` li scarica dai repository originali.

Questo repo non ospita né indicizza contenuti protetti. Quello che guardi e da dove lo guardi è responsabilità tua.

<p align="right">(<a href="#readme-top">torna su</a>)</p>

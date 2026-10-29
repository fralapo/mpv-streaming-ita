---
name: media
description: Riproduci, cerca, scarichi e tieni traccia di anime, serie TV e film tramite aw-cli (AnimeWorld/AnimeUnity) e StreamingCommunity tool. Usa quando l'utente chiede di "guardare/riprodurre" un titolo, un "episodio", di "continuare a guardare", "scarica episodi/film di", oppure parla di watchlist, AniList, Mal-Sync, cronologia di visione, StreamingCommunity.
---

# media: anime, film e serie da guardare e sincronizzare

aw-cli e lo strumento StreamingCommunity (vixsrc) sono installati e configurati.
Entrambi sono esposti agli agenti come **strumenti MCP** (server locale
`~/.local/share/media-mcp/mcp_server.py`). La watchlist di anime è sincronizzata
su **AniList** (punto di convergenza unico; nel browser la registra Mal-Sync).

## Strumenti MCP disponibili (prefisso `mcp__media__`)

Trova e usa i tool tramite la ricerca strumenti.

### Anime (aw-cli, provider AnimeWorld/AnimeUnity)
- `search` — cerca un anime; `info` — trama/dettagli; `episodes` — episodi disponibili + progresso
- `play` — riproduce con mpv sul desktop; senza `episode` continua dall'ultimo visto; aggiorna cronologia e **AniList** a fine riproduzione
- `download` — scarica in `~/Videos/Anime/<titolo>`; `offline` — scaricati; `history`/`history_remove`
- `anilist_list` — watchlist AniList completa (la lista sincronizzata col browser via Mal-Sync)
- `config_get`/`config_set` — configurazione

### Film e serie TV (StreamingCommunity)
- `sc_search` — cerca film/serie TV (ritorna titolo, tipo film/tv, imdb, index)
- `sc_episodes` — stagioni/episodi di una serie (serve PRIMA dello stream per le serie)
- `sc_stream` — riproduce con mpv (proxy locale, senza pubblicità): film senza altri argomenti; **serie TV: serve `season` + `episode`** (o `episode: "*"` per tutta la stagione, `"1-3"` per intervallo). **Senza `episode` una serie riparte automaticamente dall'episodio successivo all'ultimo guardato** (cronologia SC)
- `sc_download` — scarica in `~/Videos/StreamingCommunity/Film` (`.mkv`) o `.../Serie TV` (anche qui ripresa automatica)
- `sc_sites` — elenco siti supportati (streamingcommunity, animeworld, crunchyroll, raiplay, …)
- `sc_status` — log dell'helper per monitorare stream/download in corso (ritornano subito un pid)
- `sc_history` — cronologia contenuti SC (film e serie TV guardati/scaricati, con data)

### Router unificato
- `watch` — **sceglie automaticamente l'opzione migliore**: anime → aw-cli (con sync AniList); film/serie TV → StreamingCommunity. Parametro `kind: anime|film|serie` forza la scelta.

## Watchlist in tempo reale (a che episodio sono rimasto)

Il tool **`watchlist`** unisce in un'unica vista, sempre fresca, TUTTO ciò che riguarda la visione:
- **AniList** (browser con Mal-Sync + terminale con aw-cli): stato, progresso, `prossimo_episodio`;
- **Simkl** (`simkl_list`): serie TV, film e anime tracciati su Simkl — stesso schema: `episodio`, `stagione`, `prossimo_episodio`, `stato`; collegamento OAuth2 PKCE già fatto (app 'aw-cli helper', token con auto-refresh su 401, refresh non rotante 180gg);
- **cronologia aw-cli** (anime dal terminale);
- **attività StreamingCommunity** (film e serie TV guardati/scaricati, con `prossimo_episodio` per le serie).

Con `query` filtri per titolo (cerca in tutte le fonti); con `status` filtri per stato (CURRENT/COMPLETED/PLANNING/...).
Riprese automatiche (catena):
- anime: `play` senza `episode` continua — 1) cronologia aw-cli, 2) **AniList**, 3) **Simkl**;
- serie TV/film: `sc_stream` senza `episode` continua — 1) ultimo guardato su SC, 2) **Simkl** (es. Off Campus S1E5 → riparte da S1E6).

Esempio: `watchlist query="off campus"` → fonte simkl: Off Campus, serie tv, CURRENT, S1E5, prossimo S1E6.

## Flussi tipici

1. "riproduci l'episodio 5 di Solo Leveling": `search` → `play` query+`episode`.
2. "vediamo Interstellar": `watch` (→ StreamingCommunity film) o `sc_stream` direttamente.
3. "episodio 3 della stagione 2 di The Last of Us": `sc_episodes` per i numeri → `sc_stream` con `season: 2, episode: 3`.
4. "cosa guardo a metà?": `watchlist` (vede AniList + cronologia + SC in tempo reale) o `anilist_list`.
5. "continua The Last of Us": `sc_stream` con `season: 2` senza `episode` → riparte dal prossimo (S2E4 se l'ultimo era E3).

Regole:
- `sc_stream`/`sc_download` lanciano processi staccati e ritornano subito un `pid`: non attendere il termine; usa `sc_status`.
- `play` java lancia mpv sul desktop: non riavviare a meno che l'utente non lo chieda.
- Titoli riconosci anche scritti male; se la ricerca è ambigua usa `index` (0-based) dai risultati.

## Sincronizzazione

- **AniList** e **Simkl** sono le liste; il token Simkl ha permesso di SCRITTURA (`media:read media:write`).
- **Mal-Sync** nel browser registra su AniList (+Simkl via sync) ciò che guardi su Crunchyroll/Netflix/Prime Video — solo in QUEL verso (Crunchyroll/Netflix non accettano scritture esterne).
- **Sync inverso (da qui verso le liste, funzionante):** a fine visione mpv via aw-cli → AniList (`CURRENT`/`COMPLETED`) **e** Simkl (`simkl_mark` automatico con anilist id, numerazione piatta); a fine stream film/serie TV via SC → Simkl con imdb id. Se serve, `simkl_mark` segna manualmente un titolo.
- I film/serie TV da StreamingCommunity vanno in `~/Videos/StreamingCommunity` e vengono segnati su Simkl a fine visione.

## File utili

- Server MCP: `~/.local/share/media-mcp/mcp_server.py` (log: `server.log` nella stessa cartella)
- Helper StreamingCommunity: `~/.local/share/sc-tool/sc_helper.py` (venv: `~/.local/share/sc-tool/venv`; cartella di lavoro/config/download: `~/.local/share/sc-tool/run`; log: `run.log`)
- Config aw-cli: `~/.local/share/uv/tools/aw-cli/lib/python3.14/site-packages/aw_cli/config.toml`
- Download: `~/Videos/Anime` (anime) e `~/Videos/StreamingCommunity/{Film,Serie TV}` (film/serie)
- Nota: i tool StreamingCommunity vanno usati SOLO tramite l'helper (cwd dedicata): l'import del progetto scandaglia la cwd, e dalla home si blocca.

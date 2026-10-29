#!/usr/bin/env python3
"""
Helper per StreamingCommunity-download-stream (vixsrc/streamingcommunity ecc).

Viene eseguito SOLO con il python del venv dedicato:
    ~/.local/share/sc-tool/venv/bin/python sc_helper.py <mode> ...

E deve girare con cwd = ~/.local/share/sc-tool/run (config/download/log persistono lì).
L'import del progetto fa un os.walk(cwd) alla ricerca di device .wvd: con cwd
piccola l'import è immediato (se la cwd è la home, invece, si blocca per minuti).

Alcune modalità (stream/download) girano in foreground e vengono lanciate
"staccate" dal server MCP; altre (search/episodes/status) sono veloci.
Output: UNA riga di JSON su stdout.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

# Tutta l'output “console” del progetto va su stderr: su stdout deve esserci
# SOLO la riga JSON finale.
from rich.console import Console  # noqa: E402
_ORIG_INIT = Console.__init__


def _console_stderr(self, *a, **kw) -> None:
    kw["file"] = sys.stderr
    _ORIG_INIT(self, *a, **kw)


Console.__init__ = _console_stderr

RUN_DIR = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(RUN_DIR, "run.log")

os.environ.setdefault("STREAMING_MODE", "1")
os.environ.setdefault("STREAMING_PLAYER", "mpv")


def log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=None))
    sys.stdout.flush()


def fail(msg: str) -> None:
    log(f"ERROR: {msg}")
    out({"ok": False, "error": msg})
    sys.exit(1)


def load_functions():
    from StreamingCommunity.cli.run import load_search_functions
    return load_search_functions()


def get_func(funcs, site: str):
    key = f"{site}_search"
    f = funcs.get(key)
    if f is None:
        avail = sorted({k[:-7] for k in funcs if k.endswith("_search")})
        fail(f"Sito sconosciuto '{site}'. Disponibili: {', '.join(avail)}")
    return f


def resolve_entry(db, index, name):
    ml = db.media_list
    if not ml:
        fail("Nessun risultato")
    if index is not None:
        try:
            return ml[int(index)]
        except (ValueError, IndexError):
            fail(f"index {index} fuori range (0-{len(ml) - 1})")
    if name:
        low = name.lower()
        for m in ml:
            if m.name.lower() == low:
                return m
        for m in ml:
            if low in m.name.lower():
                return m
    return ml[0]


def entry_dict(m):
    return {
        "titolo": m.name,
        "tipo": m.type,          # film | tv
        "imdb_id": m.imdb_id,
        "url": m.url,
        "id_sito": getattr(m, "id_site", None) or getattr(m, "id", None),
    }


def cmd_sites(funcs) -> None:
    out({"ok": True, "siti": [
        {"indice": f.indice, "nome": f.module_name, "categoria": getattr(f, "use_for", "")}
        for f in funcs.values()]})


def cmd_search(funcs, site, query) -> None:
    f = get_func(funcs, site)
    db = f(query, get_onlyDatabase=True)
    ml = db.media_list
    out({"ok": True, "sito": site, "query": query,
         "risultati": len(ml), "anime": [entry_dict(m) for m in ml]})


def _parse_flags(tokens: list[str]) -> tuple[str, dict]:
    """Separa i flag (--site, --index, --season, --episode) dalla query libera."""
    flags = {}
    q, skip = [], False
    for k, a in enumerate(tokens):
        if skip:
            skip = False
            continue
        if a.startswith("--") and a in ("--site", "--index", "--season", "--episode"):
            flags[a[2:]] = tokens[k + 1]
            skip = True
        else:
            q.append(a)
    return " ".join(q), flags


def cmd_episodes(funcs, site, query, index, season) -> None:
    f = get_func(funcs, site)
    db = f(query, get_onlyDatabase=True)
    m = resolve_entry(db, index, query)
    from StreamingCommunity.services.streamingcommunity.scrapper import GetSerieInfo
    scrape = GetSerieInfo(m.imdb_id, m.name, url=m.url)
    scrape.getNumberSeason()
    seasons = []
    for s in scrape.seasons_manager.seasons:
        eps = []
        for e in scrape.getEpisodeSeasons(s.number):
            eps.append({"numero": e.number, "nome": e.name, "durata_min": e.duration})
        seasons.append({"numero": s.number, "nome": s.name, "episodi": eps})
    out({"ok": True, "titolo": m.name, "imdb_id": m.imdb_id, "stagioni": seasons})


def _resolve_and_play(funcs, site, query, index, season, episode, mode) -> None:
    f = get_func(funcs, site)
    db = f(query, get_onlyDatabase=True)
    m = resolve_entry(db, index, query)
    log(f"{mode.upper()} -> {m.name} ({m.type}) imdb={m.imdb_id}")
    kind = str(m.type).lower()
    if mode == "stream":
        from StreamingCommunity.services.streamingcommunity.downloader import (
            stream_film, stream_series,
        )
        if kind in ("film", "movie"):
            log("avvio stream film")
            stream_film(m)
            record_streamed(m.name, "film")
            out({"ok": True, "fatto": "stream_film", "titolo": m.name,
                 "imdb_id": m.imdb_id, "tipo": "film"})
        else:
            if not episode:
                auto, err = _auto_next_episode(m, season)
                if auto:
                    episode = auto
                    log(f"ripresa automatica: {m.name} -> ep {episode}")
                else:
                    fail(err)
            log(f"avvio stream serie S{season or 1}E{episode}")
            stream_series(m, str(season or 1), str(episode))
            record_streamed(m.name, "serie tv", season or 1, str(episode))
            out({"ok": True, "fatto": "stream_series", "titolo": m.name,
                 "stagione": season or 1, "episodi": str(episode) if episode != "*" else "tutti",
                 "imdb_id": m.imdb_id, "tipo": "serie tv"})
    else:  # download
        from StreamingCommunity.services.streamingcommunity.downloader import (
            download_film, download_series,
        )
        if kind in ("film", "movie"):
            res = download_film(m)
            record_streamed(m.name, "film")
            out({"ok": True, "fatto": "download_film", "titolo": m.name,
                 "file": getattr(res, "path", None) if res else None,
                 "imdb_id": m.imdb_id, "tipo": "film"})
        else:
            if not episode:
                auto, err = _auto_next_episode(m, season)
                if auto:
                    episode = auto
                    log(f"ripresa automatica download: {m.name} -> ep {episode}")
                else:
                    fail(err)
            download_series(m, str(season or 1), str(episode))
            record_streamed(m.name, "serie tv", season or 1, str(episode))
            out({"ok": True, "fatto": "download_series", "titolo": m.name,
                 "stagione": season or 1, "episodi": str(episode) if episode != "*" else "tutti",
                 "imdb_id": m.imdb_id, "tipo": "serie tv"})


def record_streamed(titolo: str, kind: str, season=None, episode=None) -> None:
    """Registra in streamed.json ogni contenuto riprodotto/scaricato, così la
    watchlist "dove ero rimasto" funziona anche per film/serie TV (SC)."""
    try:
        rec = {"titolo": titolo, "tipo": kind, "stagione": season,
               "episodi": episode, "quando": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(os.path.join(RUN_DIR, "streamed.json"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log(f"RECORDED: {titolo} {season and ('S'+str(season)) or ''}{episode and ('E'+str(episode)) or ''}")
    except Exception as e:
        log(f"record error: {e}")


def _last_streamed(titolo: str, season=None) -> dict | None:
    """Ultima attività registrata per il titolo (opz.: stagione)."""
    p = os.path.join(RUN_DIR, "streamed.json")
    if not os.path.exists(p):
        return None
    low = titolo.lower()
    last = None
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if (rec.get("titolo") or "").lower() == low:
                if season is None or str(rec.get("stagione")) == str(season):
                    last = rec
    return last


def _auto_next_episode(m, season) -> tuple[str | None, str | None]:
    """Calcola il prossimo episodio di una serie in base alla cronologia SC.
    Ritorna (episodio, errore)."""
    last = _last_streamed(m.name, season)
    seas = int(season) if season else 1
    if not last:
        return None, (f"{m.name}: nessuna cronologia. Specifica season/episode "
                      f"(o esegui 'episodes' per vedere i numeri).")
    last_ep = str(last.get("episodi") or "")
    if not last_ep.isdigit():
        return None, (f"Ultimo visto S{last.get('stagione')} {last_ep}. "
                      f"Specifica season/episode per procedere.")
    from StreamingCommunity.services.streamingcommunity.scrapper import GetSerieInfo
    scrape = GetSerieInfo(m.imdb_id, m.name, url=m.url)
    scrape.getNumberSeason()
    eps = scrape.getEpisodeSeasons(seas)
    nums = [getattr(e, "number", i + 1) for i, e in enumerate(eps)]
    nxt = int(last_ep) + 1
    if nxt in nums:
        return str(nxt), None
    if nums:
        return None, (f"Ultimo visto S{seas}E{last_ep}; il prossimo disponibile è il {max(nums)}"
                      f" (o l'ultimo {last_ep} per rivederlo). Episodi S{seas}: {nums}")
    return None, f"Nessun episodio disponibile per la stagione {seas} di {m.name}"


def cmd_history() -> None:
    items = []
    p = os.path.join(RUN_DIR, "streamed.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("{"):
                    try:
                        items.append(json.loads(line))
                    except Exception:
                        pass
    out({"ok": True, "guardati": list(reversed(items[-30:]))})


def cmd_status() -> None:
    lines = []
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8") as f:
            lines = [l.rstrip() for l in f.readlines()[-20:]]
    out({"ok": True, "log": lines})


def main() -> None:
    args = sys.argv[1:]
    if not args:
        fail("uso: sc_helper.py search|episodes|stream|download|status|sites ...")
    mode = args[0]
    try:
        if mode == "sites":
            cmd_sites(load_functions())
        elif mode == "search":
            _, site, query = args[0], args[1], " ".join(args[2:])
            cmd_search(load_functions(), site, query)
        elif mode in ("episodes", "stream", "download"):
            site = None
            idx = season = episode = None
            for k, a in enumerate(args[1:]):
                if a == "--site":
                    site = args[1 + k + 1]
                    break
            tokens = [t for t in args[1:]]
            query, flags = _parse_flags(tokens)
            site = flags.get("site") or site
            idx = flags.get("index")
            season = flags.get("season")
            episode = flags.get("episode")
            if not site or not query:
                fail(f"{mode} richiede --site e query (titolo)")
            if mode == "episodes":
                cmd_episodes(load_functions(), site, query,
                             int(idx) if idx else None, int(season) if season else None)
            else:
                _resolve_and_play(load_functions(), site, query,
                                  int(idx) if idx else None, season, episode, mode)
        elif mode == "status":
            cmd_status()
        elif mode == "history":
            cmd_history()
        else:
            fail(f"modalità sconosciuta: {mode}")
    except SystemExit:
        raise
    except BaseException as e:
        log("TRACEBACK:\n" + traceback.format_exc())
        fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()

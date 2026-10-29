#!/usr/bin/env python3
"""
MCP server (stdio) che espone aw-cli come strumento per agenti (pi, Claude Code, ecc.).

Usa direttamente l'API Python del pacchetto aw_cli (nessuna interazione fzf/TTY),
quindi gli agenti possono cercare, riprodurre, scaricare e sincronizzare.

Da eseguire con il python del venv uv di aw-cli:
  ~/.local/share/uv/tools/aw-cli/bin/python mcp_server.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from rich.console import Console

# --------------------------------------------------------------------------- #
#  Ambiente aw_cli: reindirizza tutta l'output rich verso stderr, così il      #
#  canale stdout resta pulito per il protocollo MCP.                           #
# --------------------------------------------------------------------------- #
_ORIG_CONSOLE_INIT = Console.__init__


def _console_to_stderr(self, *a: Any, **kw: Any) -> None:
    kw["file"] = sys.stderr
    _ORIG_CONSOLE_INIT(self, *a, **kw)


Console.__init__ = _console_to_stderr

import aw_cli.utilities as ut  # noqa: E402
from aw_cli import anilist  # noqa: E402
from aw_cli import download as dl  # noqa: E402
from aw_cli.anime import Anime, AnimeStatus  # noqa: E402
from aw_cli.history import History  # noqa: E402
from aw_cli.providers import create_provider  # noqa: E402

PKG_DIR = Path(ut.__file__).parent          # config.toml e history.json del pacchetto
CONFIG_PATH = PKG_DIR / "config.toml"
MPV_COMPLETE_LIMIT = 90                     # soglia % per considerare completato un episodio
PROGRESS_SAVE_SECS = 30                     # ogni quanto salvare il minutaggio durante la visione
RESUME_REWIND_SECS = 3                      # di quanto tornare indietro quando si riprende
LOG_PATH = Path.home() / ".local/share/aw-cli-tool/server.log"

ut.console = Console(highlight=False)   # il patch sopra la manda su stderr


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1_000_000:
            LOG_PATH.unlink()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def safe(fn, *args, **kwargs):
    """Esegue fn in un thread isolato, loggando qualsiasi errore."""
    def _run():
        try:
            fn(*args, **kwargs)
        except BaseException as e:
            log(f"background error in {fn.__name__}: {type(e).__name__}: {e}")
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# --------------------------------------------------------------------------- #
#  Helpers aw_cli                                                             #
# --------------------------------------------------------------------------- #
_providers: dict[str, Any] = {}


def get_provider(name: str | None = None):
    name = name or ut.config_data["provider"]["source"]
    if name not in _providers:
        _providers[name] = create_provider(name)
    return _providers[name]


def refresh_config() -> dict:
    """Rilegge config.toml da disco (così token/provider aggiornati valgono subito)."""
    ut.get_config()
    return ut.config_data


def _serialize_anime(a: Anime) -> dict:
    out = a.to_dict()
    out["dub"] = a.dub
    out["lang"] = a.info.get("Audio", "sottotitolato")
    return out


def _pick(anime_list: list[Anime], query: str, index: int | None = None) -> Anime:
    if not anime_list:
        raise ValueError(f"Nessun anime trovato per '{query}'")
    q = query.casefold()
    seen = [a.name.casefold() for a in anime_list]
    if q in seen:
        return anime_list[seen.index(q)]
    if index is not None:
        if index < 0 or index >= len(anime_list):
            raise ValueError(f"index {index} fuori range (0-{len(anime_list) - 1})")
        return anime_list[index]
    return anime_list[0]


def _resolve(query: str, index: int | None = None, provider_name: str | None = None):
    """Cerca, arricchisce con info e carica gli episodi. Ritorna (provider, anime)."""
    p = get_provider(provider_name)
    results = p.search(query)
    anime = _pick(results, query, index)
    try:
        p.info_anime(anime)
    except Exception as e:
        log(f"info_anime: {type(e).__name__}: {e}")
    if not anime.episodes():
        try:
            p.episodes(anime)
        except Exception as e:
            log(f"episodes: {type(e).__name__}: {e}")
    return p, anime


def _history() -> History:
    return History.read(str(PKG_DIR))


def _anilist_progress(token: str, user_id: int, anime_id: int) -> tuple[int | None, str | None]:
    """Progresso (ultimo episodio visto) e stato su AniList per un anime."""
    try:
        q = """query ($u: Int, $m: Int) {
            MediaList(userId: $u, mediaId: $m, type: ANIME) { progress status }
        }"""
        d = ut_http_post(token, q, {"u": user_id, "m": int(anime_id)})
        ml = (d.get("MediaList") or {}) or {}
        prog = ml.get("progress")
        st = ml.get("status")
        return (int(prog) if isinstance(prog, int) else None), st
    except BaseException as e:
        log(f"anilist_progress({anime_id}): {type(e).__name__}: {e}")
        return None, None


def _anilist_cfg_cached(cfg: dict) -> tuple[str | None, int | None]:
    a = cfg.get("anilist") or {}
    tok = a.get("token")
    uid = a.get("user_id")
    return (tok, int(uid) if isinstance(uid, int) else None)


def _target_episode(anime: Anime, episode: str | int | None,
                    cfg: dict | None = None) -> Any:
    """Risolve l'episodio da riprodurre. Senza numero esplicito:
    1) cronologia aw-cli (va avanti se l'ultimo è completato)
    2) progressione AniList dalla watchlist sincronizzata (es. guardata nel browser)
    3) primo episodio disponibile."""
    eps = anime.episodes()
    if not eps:
        raise ValueError(f"{anime.name}: nessun episodio disponibile")

    def by_num(wanted: int) -> Any | None:
        for num in eps:
            cand = anime.episode(num)
            if cand.numeric() == wanted:
                return cand
        return None

    if episode is not None:
        wanted = str(episode)
        for num in eps:
            cand = anime.episode(num)
            if num == wanted or str(cand.numeric()) == wanted:
                return cand
        raise ValueError(f"Episodio {episode} non trovato. Disponibili: {eps}")

    # 1) cronologia locale aw-cli
    hist = _history()
    for h in hist.get():
        if h.name.casefold() == anime.name.casefold():
            if anime.has_episode(h.curr_ep):
                cand = anime.episode(h.curr_ep)
                if cand.is_completed() and cand.has_next():
                    return cand.next()
                return cand
            break

    # 2) AniList (watchlist sincronizzata col browser via Mal-Sync)
    if cfg is not None:
        tok, uid = _anilist_cfg_cached(cfg)
        if tok and uid and anime.anilist_id:
            prog, st = _anilist_progress(tok, uid, anime.anilist_id)
            if prog is not None:
                prossimo = prog + 1
                cand = by_num(prossimo)
                if cand is not None:
                    log(f"continua da AniList: {anime.name} progresso={prog} -> ep {prossimo}")
                    return cand

    # 3) Simkl (se l'anime è tracciato lì)
    if cfg is not None:
        try:
            sk = _simkl_find(cfg, anime.name)
            if sk and sk.get("episodio"):
                cand = by_num(int(sk["episodio"]) + 1)
                if cand is not None:
                    log(f"continua da Simkl: {anime.name} ultimo ep {sk['episodio']} -> {cand.num}")
                    return cand
        except BaseException as e:
            log(f"_target_episode simkl: {e}")

    if anime.has_episode(anime.curr_ep):
        return anime.episode(anime.curr_ep)
    return anime.episode(eps[0])


def _anilist_update(token: str, anime_id: int, ep_num: int, status: str) -> None:
    try:
        anilist.update_anilist(token, anime_id, ep_num, status, 0, False)
        log(f"AniList update {anime_id} ep {ep_num} -> {status}")
    except BaseException as e:
        log(f"AniList update error: {type(e).__name__}: {e}")


# --------------------------------------------------------------------------- #
#  AniSkip: capitoli Opening/Ending per mpv                                    #
# --------------------------------------------------------------------------- #
ANISKIP_NAMES = {"op": "Opening", "mixed-op": "Opening", "ed": "Ending",
                 "mixed-ed": "Ending", "recap": "Recap"}


def _mal_id(anilist_id: int) -> int | None:
    import httpx
    r = httpx.post("https://graphql.anilist.co",
                   json={"query": "query($i:Int){Media(id:$i,type:ANIME){idMal}}",
                         "variables": {"i": int(anilist_id)}}, timeout=8)
    r.raise_for_status()
    return ((r.json().get("data") or {}).get("Media") or {}).get("idMal")


def _aniskip_chapters(anilist_id: int | None, ep_num: int) -> Path | None:
    """File capitoli (ffmetadata) con Opening/Ending/Recap da AniSkip, o None."""
    import httpx
    if not anilist_id:
        return None
    mal = _mal_id(anilist_id)
    if not mal:
        return None
    r = httpx.get(f"https://api.aniskip.com/v2/skip-times/{mal}/{ep_num}",
                  params=[("types", "op"), ("types", "ed"), ("types", "recap"),
                          ("episodeLength", 0)], timeout=8)
    if r.status_code != 200 or not (data := r.json()).get("found"):
        return None
    results = data.get("results") or []
    segs = sorted((x["interval"]["startTime"], x["interval"]["endTime"],
                   ANISKIP_NAMES.get(x["skipType"], x["skipType"])) for x in results)
    length = max((x.get("episodeLength") or 0) for x in results)
    chapters, pos = [], 0.0
    for start, end, name in segs:
        if start > pos + 0.5:
            chapters.append(("Episodio", pos, start))
        chapters.append((name, start, end))
        pos = end
    if length and pos < length - 2:
        chapters.append(("Episodio", pos, length))
    elif not length and chapters and chapters[-1][0] != "Ending":
        chapters.append(("Episodio", pos, pos + 86400))
    lines = [";FFMETADATA1"]
    for title, start, end in chapters:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(start * 1000)}",
                  f"END={int(end * 1000)}", f"title={title}"]
    path = Path(tempfile.gettempdir()) / f"awcli-chapters-{mal}-{ep_num}.ffmeta"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
#  IPC mpv: posizione e durata esatte (più affidabile del log a terminale)     #
# --------------------------------------------------------------------------- #
def _ipc_watch(sock_path: str, state: dict, proc: subprocess.Popen) -> None:
    import socket
    s = None
    for _ in range(100):
        if proc.poll() is not None:
            return
        try:
            s = socket.socket(socket.AF_UNIX)
            s.connect(sock_path)
            break
        except OSError:
            s.close()
            s = None
            time.sleep(0.2)
    if s is None:
        return
    with s:
        for i, prop in enumerate(("time-pos", "duration", "percent-pos"), 1):
            s.sendall((json.dumps({"command": ["observe_property", i, prop]}) + "\n").encode())
        buf = b""
        while chunk := s.recv(65536):
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for line in lines:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("event") == "property-change" and ev.get("data") is not None:
                    state[ev["name"]] = ev["data"]


# --------------------------------------------------------------------------- #
#  Tracking in background dopo la riproduzione mpv                             #
# --------------------------------------------------------------------------- #
def _track_playback(anime: Anime, ep, proc: subprocess.Popen, logfile: Path,
                    private: bool, history: History, token: str | None,
                    cfg: dict | None = None, ipc_state: dict | None = None) -> None:
    # Salvataggio periodico: se mpv o l'MCP si chiudono male si perde al massimo PROGRESS_SAVE_SECS
    while True:
        try:
            proc.wait(timeout=PROGRESS_SAVE_SECS)
            break
        except subprocess.TimeoutExpired:
            if private or not ipc_state or ipc_state.get("time-pos") is None:
                continue
            try:
                ep.set_progress(int(ipc_state["time-pos"]))
                history.update(anime, ep)
            except Exception as e:
                log(f"salvataggio periodico: {e}")
    try:
        text = logfile.read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""
    completed, progress = False, 0
    if ipc_state and ipc_state.get("time-pos") is not None:
        progress = int(ipc_state["time-pos"])
        pct = ipc_state.get("percent-pos")
        if pct is None and ipc_state.get("duration"):
            pct = 100 * ipc_state["time-pos"] / ipc_state["duration"]
        completed = (pct or 0) >= MPV_COMPLETE_LIMIT
    elif res := re.findall(r"(\d+):(\d+):(\d+) / [\d:]+ \((\d+)%\)", text):
        last = res[-1]
        h, m, s, pct = (int(x) for x in last)
        progress = h * 3600 + m * 60 + s
        completed = pct >= MPV_COMPLETE_LIMIT
    try:
        ep.set_progress(progress)
        if completed:
            ep.mark_completed()
    except Exception:
        pass
    anime.curr_ep = ep.num
    if not private:
        try:
            history.update(anime, ep)
        except Exception as e:
            log(f"history.update: {e}")
        if completed:
            # AniList (push di progresso/completamento)
            if token and anime.anilist_id:
                status = "COMPLETED" if (
                    str(ep.numeric()) == str(anime.last_ep)
                    and anime.status == AnimeStatus.FINISHED
                ) else "CURRENT"
                _anilist_update(token, anime.anilist_id, int(ep.numeric()), status)
            # Simkl (sync inverso: l'episodio visto qui arriva anche su Simkl)
            if cfg is not None and anime.anilist_id:
                try:
                    safe(_simkl_mark, cfg, "anime", "anilist", anime.anilist_id,
                         episode=int(ep.numeric()))
                except BaseException as e:
                    log(f"simkl push anime: {type(e).__name__}: {e}")
    log(f"playback done: {anime.name} ep {ep.num} prog={progress}s completed={completed}")


# --------------------------------------------------------------------------- #
#  Tool implementations                                                        #
# --------------------------------------------------------------------------- #
def t_search(args: dict) -> dict:
    refresh_config()
    p = get_provider(args.get("provider"))
    results = p.search(str(args["query"]))
    return {"risultati": len(results),
            "anime": [_serialize_anime(a) for a in results]}


def t_latest(args: dict) -> dict:
    refresh_config()
    p = get_provider(args.get("provider"))
    filtro = args.get("filter", "a")
    results = p.latest(filtro)
    out = []
    for a in results:
        d = _serialize_anime(a)
        d.pop("episodes", None)
        out.append(d)
    return {"filter": filtro, "anime": out}


def t_info(args: dict) -> dict:
    refresh_config()
    _, anime = _resolve(args["query"], args.get("index"), args.get("provider"))
    return _serialize_anime(anime)


def t_episodes(args: dict) -> dict:
    refresh_config()
    _, anime = _resolve(args["query"], args.get("index"), args.get("provider"))
    cfg = refresh_config()
    hist = _history()
    storico = None
    for h in hist.get():
        if h.name.casefold() == anime.name.casefold():
            storico = h
            break
    tok, uid = _anilist_cfg_cached(cfg)
    al_prog, al_st = None, None
    if tok and uid and anime.anilist_id:
        al_prog, al_st = _anilist_progress(tok, uid, anime.anilist_id)
    eps = []
    for num in anime.episodes():
        ep = anime.episode(num)
        eps.append({"episodio": num, "numerico": ep.numeric(),
                    "progresso_sec": ep.progress, "completato": ep.is_completed()})
    return {"anime": anime.name, "stato": anime.status.value,
            "last_ep": anime.last_ep, "curr_ep": anime.curr_ep,
            "in_cronologia": storico is not None,
            "anilist_progresso": al_prog, "anilist_stato": al_st,
            "da_dove_riprendere": (al_prog + 1) if al_prog is not None else (
                storico.curr_ep if storico else None),
            "episodi": eps}


def t_play(args: dict) -> dict:
    cfg = refresh_config()
    provider, anime = _resolve(args["query"], args.get("index"), args.get("provider"))
    ep = _target_episode(anime, args.get("episode"), cfg)
    private = bool(args.get("private", False))

    ep_url = provider.episode_link(anime, ep)
    player = cfg["player"]["path"]
    logfile = Path(tempfile.gettempdir()) / f"awcli-mpv-{int(time.time() * 1000)}.log"
    sock = str(Path(tempfile.gettempdir()) / f"awcli-mpv-{int(time.time() * 1000)}.sock")
    cmd = [player, ep_url,
           f"--force-media-title={anime.name} - {ep}",
           f"--start={max(0, ep.progress - RESUME_REWIND_SECS)}",
           f"--input-ipc-server={sock}",
           "--profile=pip" if args.get("popup") else "--fullscreen", "--keep-open"]
    skip_info = "nessun dato AniSkip"
    try:
        chapters = _aniskip_chapters(anime.anilist_id, int(ep.numeric()))
        if chapters:
            cmd.append(f"--chapters-file={chapters}")
            skip_info = "capitoli Opening/Ending da AniSkip (TAB per saltare)"
    except BaseException as e:
        log(f"aniskip: {type(e).__name__}: {e}")
    proc = subprocess.Popen(cmd, stdout=logfile.open("w"),
                            stderr=subprocess.STDOUT, start_new_session=True)
    ipc_state: dict = {}
    safe(_ipc_watch, sock, ipc_state, proc)
    log(f"avviato mpv pid={proc.pid} per {anime.name} ep {ep.num} (private={private}, {skip_info})")

    token = None
    if not private:
        anime.curr_ep = ep.num
        history = _history()
        try:
            history.update(anime, ep)
        except Exception as e:
            log(f"history.update: {e}")
        if "anilist" in cfg and cfg["anilist"].get("token"):
            token = cfg["anilist"]["token"]
            safe(_anilist_update, token, anime.anilist_id, int(ep.numeric()), "CURRENT")
        safe(_track_playback, anime, ep, proc, logfile, private, history, token, cfg, ipc_state)

    return {"anime": anime.name, "episodio": ep.num, "titolo": str(ep),
            "url": ep_url, "player": player, "mpv_pid": proc.pid, "skip": skip_info,
            "nota": "mpv è partito; progresso e AniList vengono aggiornati a fine riproduzione"}


def t_download(args: dict) -> dict:
    refresh_config()
    provider, anime = _resolve(args["query"], args.get("index"), args.get("provider"))
    wanted = args.get("episodes") or []
    if not wanted:
        raise ValueError("Specifica gli episodi da scaricare, es. [1, 2, 3]")
    eps = []
    for w in wanted:
        eps.append(_target_episode(anime, w))
    base = dl.path(create=True)
    before = set(base.glob(f"{anime.name}/*.mp4")) if (base / anime.name).exists() else set()
    dl.episodes(anime, eps, provider)
    after = set(base.glob(f"{anime.name}/*.mp4"))
    nuovi = sorted(str(p.relative_to(base)) for p in (after - before))
    return {"cartella": str(base / anime.name), "scaricati": nuovi}


def t_offline(args: dict) -> dict:
    root = dl.path(create=False)
    out = []
    if root.exists():
        for d in sorted([p for p in root.iterdir() if p.is_dir()]):
            vids = sorted(d.glob("*.mp4"))
            if vids:
                out.append({"anime": d.name, "episodi": [v.stem.split(" - ")[-1] for v in vids],
                            "cartella": str(d)})
    return {"qualcosa_da_vedere": len(out) > 0, "anime": out}


def t_history(args: dict) -> dict:
    hist = _history()
    out = []
    for a in hist.get():
        d = _serialize_anime(a)
        d.pop("episodes", None)
        out.append(d)
    return {"cronologia": out}


def t_history_remove(args: dict) -> dict:
    refresh_config()
    hist = _history()
    q = args["query"].casefold()
    match = None
    for a in hist.get():
        if a.name.casefold() == q:
            match = a
            break
    if match is None and args.get("index") is not None:
        all_a = hist.get()
        i = args["index"]
        if 0 <= i < len(all_a):
            match = all_a[i]
    if match is None:
        raise ValueError(f"{args['query']} non è nella cronologia")
    hist.remove(match)
    return {"rimosso": match.name}


def t_anilist_list(args: dict) -> dict:
    cfg = refresh_config()
    token = args.get("token") or cfg.get("anilist", {}).get("token")
    if not token:
        raise ValueError("Token AniList non configurato. Usa config_set con anilist.token o passa token=...")
    status = args.get("status")  # CURRENT|COMPLETED|PLANNING|DROPPED|PAUSED|REPEATING
    query = """
    query ($userId: Int, $status: MediaListStatus, $sort: [MediaListSort]) {
      MediaListCollection(userId: $userId, type: ANIME, status: $status, sort: $sort) {
        lists { entries {
          progress score status
          media { id title { romaji english native } episodes }
        } }
      }
    }
    """
    user_id = anilist.get_user_id(token)
    var: dict = {"userId": user_id, "sort": ["UPDATED_TIME_DESC"]}
    if status:
        var["status"] = status
    r = ut_http_post(token, query, var)
    entries = []
    for lst in (r.get("MediaListCollection") or {}).get("lists") or []:
        for e in lst.get("entries") or []:
            m = e.get("media") or {}
            title = ((m.get("title") or {}) or {}).get("romaji") or ((m.get("title") or {}).get("english"))
            entries.append({
                "titolo": title, "anilist_id": m.get("id"),
                "stato": e.get("status"), "progresso": e.get("progress"),
                "totale": m.get("episodes"), "voto": e.get("score"),
            })
    return {"userId": user_id, "lista": entries}


def ut_http_post(token: str, query: str, var: dict) -> dict:
    import httpx
    r = httpx.post("https://graphql.anilist.co",
                   headers={"Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            "Accept": "application/json"},
                   json={"query": query, "variables": var}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise ValueError(f"AniList API: {data['errors']}")
    return data.get("data") or {}


def t_config_get(args: dict) -> dict:
    cfg = refresh_config()
    anilist_cfg = cfg.get("anilist", {})
    player = cfg.get("player", {})
    general = cfg.get("general", {})
    return {
        "player": {"type": player.get("type"), "path": player.get("path")},
        "provider": cfg.get("provider", {}).get("source"),
        "special": general.get("specials") if "specials" in general else False,
        "anilist_configurato": bool(anilist_cfg.get("token")),
        "anilist_utente_id": anilist_cfg.get("user_id"),
        "simkl_configurato": bool((cfg.get("simkl") or {}).get("access_token")),
        "syncplay_configurato": bool(cfg.get("syncplay")),
        "versione": __import__("importlib.metadata", fromlist=["version"]).version("aw-cli"),
        "cartella_download": str(dl.path(create=False)),
        "cartella_config": str(PKG_DIR),
    }


def t_config_set(args: dict) -> dict:
    cfg = refresh_config()
    key = str(args["key"])
    value = args["value"]
    changed: list[str] = []
    if key == "provider.source":
        if value not in ("animeworld", "animeunity"):
            raise ValueError("provider: animeworld o animeunity")
        cfg["provider"]["source"] = value
        _providers.pop(value, None)
        changed.append(f"provider={value}")
    elif key == "general.specials":
        cfg["general"]["specials"] = bool(value)
        changed.append(f"specials={value}")
    elif key == "player.type":
        cfg["player"]["type"] = str(value)
        if value == "mpv":
            cfg["player"]["path"] = shutil_which("mpv") or cfg["player"]["path"]
        elif value == "vlc":
            cfg["player"]["path"] = shutil_which("vlc") or cfg["player"]["path"]
        changed.append(f"player={value}")
    elif key == "player.path":
        cfg["player"]["path"] = str(value)
        changed.append(f"player.path={value}")
    elif key == "anilist.token":
        token = str(value).strip()
        user_id = anilist.get_user_id(token)   # valida e ricava l'id
        cfg["anilist"] = {"token": token, "user_id": user_id,
                          "rating": False, "favorite": False, "drop": False}
        changed.append(f"anilist.token OK (user_id={user_id})")
    elif key == "anilist.clear":
        cfg.pop("anilist", None)
        changed.append("anilist rimosso")
    elif key.startswith("simkl."):
        k = key.split(".", 1)[1]
        if k == "clear":
            cfg.pop("simkl", None)
            changed.append("simkl rimosso")
        elif k in ("client_id", "client_secret", "access_token", "refresh_token"):
            cfg.setdefault("simkl", {})[k] = str(value)
            changed.append(f"simkl.{k} impostato")
        else:
            raise ValueError(f"Chiave simkl non supportata: {k}")
    else:
        raise ValueError(f"Chiave non supportata: {key}")
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        ut.toml.dump(cfg, f)
    return {"modificato": changed}


def shutil_which(name: str):
    import shutil
    return shutil.which(name)


# --------------------------------------------------------------------------- #
#  Simkl (watchlist film/serie/anime, oltre ad AniList)  — AUTH V2             #
# --------------------------------------------------------------------------- #
SIMKL_API = "https://api.simkl.com"
OOB_REDIRECT = "http://localhost:9876/callback"
SIMKL_APP = "aw-cli-mcp"
SIMKL_VER = "1.0"


def _simkl_cfg(cfg: dict) -> tuple[str | None, str | None]:
    s = cfg.get("simkl") or {}
    cid = s.get("client_id")
    tok = s.get("access_token")
    return (str(cid) if cid else None, str(tok) if tok else None)


def _save_config(cfg: dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        ut.toml.dump(cfg, f)


def _simkl_refresh(cfg: dict) -> str | None:
    """Rinnova l'access token (refresh non-rotante, 180gg). Ritorna il nuovo
    access token oppure None. Un solo owner (questo server) fa i refresh."""
    s = cfg.get("simkl") or {}
    if not s.get("refresh_token"):
        return None
    import httpx
    try:
        r = httpx.post(SIMKL_API + "/oauth2/token", data={
            "grant_type": "refresh_token",
            "client_id": s.get("client_id"),
            "refresh_token": s.get("refresh_token"),
        }, headers={"User-Agent": f"{SIMKL_APP}/{SIMKL_VER}",
                   "Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        if r.status_code != 200:
            log(f"simkl refresh HTTP {r.status_code}: {r.text[:120]}")
            return None
        j = r.json()
        s["access_token"] = str(j.get("access_token"))
        if j.get("refresh_token"):
            s["refresh_token"] = str(j["refresh_token"])
        _save_config(cfg)
        log("Simkl access token rinnovato")
        return s["access_token"]
    except BaseException as e:
        log(f"simkl refresh error: {type(e).__name__}: {e}")
        return None


def _simkl_get(cfg: dict, path: str, params: dict | None = None, retry: bool = True) -> dict:
    import httpx
    cid, tok = _simkl_cfg(cfg)
    if not cid or not tok:
        raise ValueError("Simkl non configurato (client_id/access_token mancanti)")
    q = dict(params or {})
    q.update({"client_id": cid, "app-name": SIMKL_APP, "app-version": SIMKL_VER})
    headers = {"User-Agent": f"{SIMKL_APP}/{SIMKL_VER}"}
    if tok:
        headers["Authorization"] = "Bearer " + tok
    r = httpx.get(SIMKL_API + path, params=q, headers=headers, timeout=30)
    if r.status_code == 401 and retry:
        new = _simkl_refresh(cfg)
        if new:
            headers["Authorization"] = "Bearer " + new
            r = httpx.get(SIMKL_API + path, params=q, headers=headers, timeout=30)
    if r.status_code in (401, 403):
        raise ValueError(f"Simkl non autorizzato: {r.text[:120]}")
    r.raise_for_status()
    return r.json()


def _simkl_mark(cfg: dict, kind: str, id_key: str, id_val, season=None, episode=None,
                retry: bool = True) -> dict:
    """Segna come visto su Simkl (POST /sync/history). kind: film | serie tv | anime.
    id_key/id_val: es. ("anilist", 176301) oppure ("simkl", 2597547) oppure ("imdb", ...).
    Per gli anime l'episodio è numerazione piatta (AniDB-sequential); per serie TV serve
    anche la stagione."""
    import httpx
    cid, tok = _simkl_cfg(cfg)
    if not cid or not tok:
        raise ValueError("Simkl non configurato")
    q = {"client_id": cid, "app-name": SIMKL_APP, "app-version": SIMKL_VER}
    headers = {"User-Agent": f"{SIMKL_APP}/{SIMKL_VER}",
               "Authorization": "Bearer " + tok, "Content-Type": "application/json"}
    body: dict = {}
    if kind == "film":
        body["movies"] = [{"ids": {id_key: str(id_val)}}]
    else:
        item: dict = {"ids": {id_key: str(id_val)}}
        if episode is not None:
            ep_list = [{"number": int(episode)}]
            if kind in ("serie tv", "serie") and season is not None:
                item["seasons"] = [{"number": int(season), "episodes": ep_list}]
            else:
                item["episodes"] = ep_list
        body["shows"] = [item]

    def _post():
        return httpx.post(SIMKL_API + "/sync/history", params=q, headers=headers,
                          json=body, timeout=30)
    r = _post()
    if r.status_code == 401 and retry:
        new = _simkl_refresh(cfg)
        if new:
            headers["Authorization"] = "Bearer " + new
            r = _post()
    if r.status_code not in (200, 201):
        raise ValueError(f"Simkl mark HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    added = j.get("added") or {}
    notf = j.get("not_found") or {}
    log(f"simkl_mark {kind} {id_key}={id_val} s={season} e={episode} -> "
        f"added={json.dumps(added)[:80]} not_found={json.dumps(notf)[:80]}")
    return {"ok": True, "added": added, "not_found": notf, "risposta": j}

def _simkl_watchlist_items(cfg: dict) -> list[dict]:
    """Watchlist Simkl (AUTH V2): serie TV, anime e film con progresso."""
    data = _simkl_get(cfg, "/sync/all-items/")
    items: list[dict] = []
    STATUS_MAP = {"watching": "CURRENT", "completed": "COMPLETED",
                  "plantowatch": "PLANNING", "hold": "PAUSED", "dropped": "DROPPED"}

    def parse_lw(lw) -> tuple[int | None, int | None]:
        m = re.fullmatch(r"S(\d+)E(\d+)", lw or "")
        if m:
            return (int(m.group(1)), int(m.group(2)))
        m2 = re.fullmatch(r"E(\d+)", lw or "")   # anime: episodio senza stagione
        if m2:
            return (1, int(m2.group(1)))
        return (None, None)

    def proc(entry: dict, kind: str) -> None:
        obj = entry.get("show") or entry.get("movie") or {}
        lw = entry.get("last_watched")
        sn, en = parse_lw(lw)
        if lw is None and (entry.get("watched_episodes_count") or 0) > 0:
            sn2, en2 = parse_lw(entry.get("next_to_watch"))
            if en2:
                sn, en = sn2, en2 - 1
        items.append({"titolo": obj.get("title"), "tipo": kind,
                      "stato": STATUS_MAP.get(str(entry.get("status")), entry.get("status")),
                      "id_simkl": (obj.get("ids") or {}).get("simkl"),
                      "stagione": sn, "episodio": en,
                      "progresso": entry.get("watched_episodes_count"),
                      "totale": entry.get("total_episodes_count"),
                      "prossimo_episodio": (en + 1) if en else None,
                      "sorgente": "simkl"})

    for e in data.get("shows") or []:
        proc(e, "serie tv")
    for e in data.get("anime") or []:
        proc(e, "anime")
    for e in data.get("movies") or []:
        proc(e, "film")
    return items


import http.server  # noqa: E402
import urllib.parse  # noqa: E402
import webbrowser  # noqa: E402


def _simkl_find(cfg: dict, titolo: str) -> dict | None:
    """Trova un titolo nella watchlist Simkl (matching case-insensitive)."""
    low = titolo.casefold()
    items = _simkl_watchlist_items(cfg)
    for it in items:
        if (it.get("titolo") or "").casefold() == low:
            return it
    for it in items:
        if low in (it.get("titolo") or "").casefold():
            return it
    return None


def t_simkl_auth(args: dict) -> dict:
    """OAuth V2 con PKCE: apre il browser su /oauth2/authorize, cattura il codice
    sul localhost, lo scambia e salva access+refresh token."""
    import socket
    import base64 as _b64
    import hashlib as _h
    import secrets as _sec
    from threading import Thread

    cfg = refresh_config()
    s = cfg.get("simkl") or {}
    cid = s.get("client_id")
    if not cid:
        raise ValueError("Prima imposta simkl.client_id con config_set")

    # PKCE S256
    verifier = _sec.token_urlsafe(64)
    challenge = _b64.urlsafe_b64encode(
        _h.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    code_holder: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.urlparse(self.path)
            if q.path == "/callback":
                params = urllib.parse.parse_qs(q.query)
                code_holder["code"] = params.get("code", [""])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>OK, puoi chiudere questa scheda.</h2>")
            else:
                self.send_response(404); self.end_headers()
        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 9876), H)
    Thread(target=srv.serve_forever, daemon=True).start()
    url = (f"https://simkl.com/oauth2/authorize?client_id={cid}"
           f"&redirect_uri={urllib.parse.quote(OOB_REDIRECT, safe='')}"
           f"&response_type=code&code_challenge={challenge}"
           f"&code_challenge_method=S256&state=pi-aw")
    webbrowser.open(url)
    t0 = time.time()
    while "code" not in code_holder and time.time() - t0 < 120:
        time.sleep(0.3)
    srv.shutdown()
    code = code_holder.get("code")
    if not code:
        raise ValueError("Timeout: nessun codice ricevuto (autorizza nel browser)")
    import httpx
    r = httpx.post(SIMKL_API + "/oauth2/token", json={
        "client_id": cid, "code": code, "code_verifier": verifier,
        "redirect_uri": OOB_REDIRECT, "grant_type": "authorization_code"},
        headers={"User-Agent": f"{SIMKL_APP}/{SIMKL_VER}"}, timeout=30)
    if r.status_code != 200:
        raise ValueError(f"Scambio fallito: {r.text[:200]}")
    j = r.json()
    s["access_token"] = str(j.get("access_token"))
    if j.get("refresh_token"):
        s["refresh_token"] = str(j["refresh_token"])
    cfg["simkl"] = s
    _save_config(cfg)
    log("Simkl OAuth2 completato (token salvato)")
    return {"ok": True, "token_salvato": True,
            "nota": "I dati Simkl ora compaiono nella fonte simkl della watchlist"}


def t_simkl_mark(args: dict) -> dict:
    """Segna come visto un titolo su Simkl (sync inverso)."""
    cfg = refresh_config()
    it = _simkl_find(cfg, args["query"])
    if not it:
        raise ValueError(f"'{args['query']}' non trovato nella watchlist Simkl")
    kind = it.get("tipo")
    sid = it.get("id_simkl")
    if kind == "film":
        return _simkl_mark(cfg, "film", "simkl", sid)
    season = args.get("season")
    episode = args.get("episode")
    if episode is None:
        # segna solo up-to-current: usa il prossimo? meglio richiedere l'episodio
        raise ValueError("Per serie/anime indica episode (e season per le serie tv)")
    k = "serie tv" if kind == "serie tv" else "anime"
    return _simkl_mark(cfg, k, "simkl", sid, season=season, episode=episode)


def t_simkl_list(args: dict) -> dict:
    cfg = refresh_config()
    items = _simkl_watchlist_items(cfg)
    if not items:
        return {"ok": False, "nota": "Simkl non configurato o lista vuota. Imposta simkl.client_id/secret e lancia simkl_auth"}
    q = (args.get("query") or "").casefold()
    if q:
        items = [i for i in items if q in (i.get("titolo") or "").casefold()]
    return {"ok": True, "totale": len(items), "titoli": items}


# --------------------------------------------------------------------------- #
#  StreamingCommunity (helper in venv dedicato ~/.local/share/sc-tool)         #
# --------------------------------------------------------------------------- #
SC_PY = "/home/lapo/.local/share/sc-tool/venv/bin/python"
SC_HELPER = "/home/lapo/.local/share/sc-tool/sc_helper.py"
SC_RUN = "/home/lapo/.local/share/sc-tool/run"
SC_PROC: dict[int, subprocess.Popen] = {}


def _sc_json(tail: str) -> dict | None:
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def sc_call(args: list[str], timeout: int = 150) -> dict:
    """Esegue l'helper in foreground (search/episodes/sites/status)."""
    p = subprocess.run([SC_PY, SC_HELPER, *args], cwd=SC_RUN,
                       capture_output=True, text=True, timeout=timeout)
    d = _sc_json(p.stdout)
    if d is None:
        raise ValueError(f"sc_helper fallito rc={p.returncode}: "
                         f"{(p.stdout + p.stderr)[-400:]}")
    return d


def sc_spawn(args: list[str], env: dict | None = None) -> subprocess.Popen:
    """Lancia stream/download in un processo staccato dalla sessione MCP."""
    from pathlib import Path as _P
    out_p = _P(tempfile.gettempdir()) / f"sc-{int(time.time() * 1000)}.out"
    err_p = _P(tempfile.gettempdir()) / f"sc-{int(time.time() * 1000)}.err"
    with out_p.open("w"), err_p.open("w"):
        pass
    p = subprocess.Popen([SC_PY, SC_HELPER, *args], cwd=SC_RUN,
                         stdin=subprocess.DEVNULL,
                         stdout=out_p.open("w"), stderr=err_p.open("w"),
                         env={**os.environ, **(env or {})},
                         start_new_session=True)
    p._sc_out = out_p
    p._sc_err = err_p
    SC_PROC[p.pid] = p
    log(f"sc_spawn pid={p.pid} args={args}")
    return p


def _sc_run_or_report(args: list[str], verb: str, env: dict | None = None) -> dict:
    """Avvia l'azione; se il processo muore subito (es. episodio mancante per
    una serie) riporta subito l'errore invece di lasciare l'agente al buio."""
    p = sc_spawn(args, env)
    for _ in range(12):
        if p.poll() is not None:
            break
        time.sleep(0.5)
    if p.poll() is None:
        return {"ok": True, "azione": verb, "pid": p.pid,
                "nota": f"{verb} in corso (pid {p.pid}); controlla con sc_status"}
    try:
        out_txt = getattr(p, "_sc_out", None) and p._sc_out.read_text(
            encoding="utf-8", errors="replace")
        err_txt = getattr(p, "_sc_err", None) and p._sc_err.read_text(
            encoding="utf-8", errors="replace")
    except Exception:
        out_txt, err_txt = "", ""
    d = _sc_json(out_txt or "")
    if d and not d.get("ok", True):
        return {"ok": False, "errore": d.get("error")}
    if d:
        return d
    return {"ok": False, "errore": f"{verb} fallito subito (rc={p.returncode}): {(err_txt or '')[-250:]}"}


def t_sc_sites(args: dict) -> dict:
    return sc_call(["sites"])


def t_sc_search(args: dict) -> dict:
    out = sc_call(["search", str(args.get("site", "streamingcommunity")),
                   str(args["query"])])
    out["suggerimento"] = "usa l'indice (index) per disambiguare; per serie TV usa sc_episodes"
    return out


def t_sc_episodes(args: dict) -> dict:
    cmd = ["episodes", "--site", str(args.get("site", "streamingcommunity")),
           str(args["query"])]
    if args.get("index") is not None:
        cmd += ["--index", str(args["index"])]
    return sc_call(cmd)


def t_sc_stream(args: dict) -> dict:
    cfg = refresh_config()
    query = str(args["query"])
    episode = args.get("episode")
    season = args.get("season")
    if episode is None:
        try:
            sk = _simkl_find(cfg, query)
            if sk and sk.get("episodio") and (season is None
                                               or str(sk.get("stagione")) == str(season)):
                episode = int(sk["episodio"]) + 1
                log(f"sc_stream continua da Simkl: {query} -> ep {episode} "
                    f"(stagione {sk.get('stagione')})")
                if season is None:
                    season = sk.get("stagione")
        except BaseException as e:
            log(f"sc_stream simkl lookup: {e}")
    cmd = ["stream", "--site", str(args.get("site", "streamingcommunity")), query]
    if args.get("index") is not None:
        cmd += ["--index", str(args["index"])]
    if season is not None:
        cmd += ["--season", str(season)]
    if episode is not None:
        cmd += ["--episode", str(episode)]
    # popup: mpv legge la config di ~/.config/mpv-pip (profilo pip, finestra fissa in basso a destra)
    env = {"MPV_HOME": str(Path.home() / ".config/mpv-pip")} if args.get("popup") else None
    res = _sc_run_or_report(cmd, "stream", env)
    if res.get("ok") and res.get("pid"):
        proc = SC_PROC.get(res["pid"])
        if proc is not None:
            safe(_sc_watch_simkl, proc, cfg)
    return res


def t_sc_download(args: dict) -> dict:
    cmd = ["download", "--site", str(args.get("site", "streamingcommunity")),
           str(args["query"])]
    if args.get("index") is not None:
        cmd += ["--index", str(args["index"])]
    if args.get("season") is not None:
        cmd += ["--season", str(args["season"])]
    if args.get("episode") is not None:
        cmd += ["--episode", str(args["episode"])]
    return _sc_run_or_report(cmd, "download")


def _sc_watch_simkl(p: subprocess.Popen, cfg: dict) -> None:
    """A fine stream SC (player chiuso), segna su Simkl l'episodio/film visto."""
    p.wait()
    try:
        out_p = getattr(p, "_sc_out", None)
        txt = out_p.read_text(encoding="utf-8", errors="replace") if out_p else ""
    except Exception:
        return
    d = _sc_json(txt or "")
    if not d or not d.get("ok") or not d.get("imdb_id"):
        return
    fatto = str(d.get("fatto", ""))
    if not fatto.startswith("stream"):
        return
    ep = str(d.get("episodi") or "")
    if d.get("tipo") == "film" or fatto == "stream_film":
        try:
            _simkl_mark(cfg, "film", "imdb", d["imdb_id"])
        except BaseException as e:
            log(f"simkl push film: {e}")
        return
    if ep.isdigit():
        try:
            _simkl_mark(cfg, "serie tv", "imdb", d["imdb_id"],
                        season=int(d.get("stagione") or 1) if d.get("stagione") else None,
                        episode=int(ep))
        except BaseException as e:
            log(f"simkl push serie: {e}")


def t_sc_status(args: dict) -> dict:
    return sc_call(["status"], timeout=30)


def t_sc_history(args: dict) -> dict:
    """Ultimi contenuti riprodotti/scaricati tramite StreamingCommunity tool."""
    return sc_call(["history"], timeout=30)


def t_watchlist(args: dict) -> dict:
    """Vista unificata in tempo reale di tutta la watchlist: AniList (browser+
    terminale) + cronologia aw-cli + attività StreamingCommunity.
    Con query filtra per titolo e indica a che episodio sei rimasto."""
    cfg = refresh_config()
    query = (args.get("query") or "").strip().casefold()
    status_filter = args.get("status")  # CURRENT|COMPLETED|PLANNING|...
    out: dict = {"ok": True, "aggiornata_il": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "fonti": []}

    # --- AniList (watchlist principale, in tempo reale) ---
    al_items: list[dict] = []
    tok, uid = _anilist_cfg_cached(cfg)
    if tok and uid:
        try:
            q = """query ($userId: Int, $status: MediaListStatus, $sort: [MediaListSort]) {
              MediaListCollection(userId: $userId, type: ANIME, status: $status, sort: $sort) {
                lists { entries {
                  progress score status
                  media { id title { romaji english } episodes }
                } }
              }
            }"""
            var: dict = {"userId": uid, "sort": ["UPDATED_TIME_DESC"]}
            if status_filter:
                var["status"] = status_filter
            d = ut_http_post(tok, q, var)
            for lst in (d.get("MediaListCollection") or {}).get("lists") or []:
                for e in lst.get("entries") or []:
                    m = e.get("media") or {}
                    title = ((m.get("title") or {}) or {}).get("romaji") or \
                            ((m.get("title") or {}).get("english"))
                    prog = e.get("progress")
                    tot = m.get("episodes")
                    al_items.append({
                        "titolo": title, "anilist_id": m.get("id"),
                        "stato": e.get("status"), "progresso": prog,
                        "totale": tot, "voto": e.get("score"),
                        "prossimo_episodio": (prog + 1) if isinstance(prog, int)
                                             and (tot is None or prog < tot) else None,
                        "sorgente": "anilist",
                    })
        except BaseException as e:
            log(f"watchlist anilist: {e}")

    # --- cronologia locale aw-cli ---
    hist_items: list[dict] = []
    try:
        for h in _history().get():
            hist_items.append({"titolo": h.name, "stato": h.status.value,
                               "episodio_corrente": h.curr_ep,
                               "sorgente": "aw-cli",
                               "quando": None})
    except BaseException as e:
        log(f"watchlist history: {e}")

    # --- Simkl (film/serie/anime tracciati sull'app Simkl) ---
    simkl_items: list[dict] = []
    try:
        simkl_items = _simkl_watchlist_items(cfg)
    except BaseException as e:
        log(f"watchlist simkl: {e}")

    # --- attività StreamingCommunity (episodi guardati/scaricati) ---
    sc_items: list[dict] = []
    try:
        d = sc_call(["history"], timeout=30)
        if d.get("ok"):
            for it in d.get("guardati", []):
                e = str(it.get("episodi") or "")
                if it.get("tipo") == "serie tv" and e.isdigit():
                    it = dict(it)
                    it["prossimo_episodio"] = int(e) + 1
                sc_items.append(it)
    except BaseException as e:
        log(f"watchlist sc: {e}")

    def _match(titoli: list, q: str) -> list:
        if not q:
            return titoli
        return [t for t in titoli if q in (t.get("titolo") or "").casefold()
                or q in ((t.get("titolo") or "")).casefold()]

    al_f, h_f = _match(al_items, query), _match(hist_items, query)
    sk_f = _match(simkl_items, query) if query else simkl_items
    sc_f = _match(sc_items, query) if query else sc_items
    out["fonti"] = [
        {"nome": "anilist", "titoli": al_f},
        {"nome": "simkl", "titoli": sk_f},
        {"nome": "aw-cli_cronologia", "titoli": h_f},
        {"nome": "streamingcommunity", "attivita": sc_f},
    ]
    out["conteggi"] = {"anilist": len(al_items), "simkl": len(simkl_items),
                        "aw-cli": len(hist_items),
                        "streamingcommunity": len(sc_items)}
    if query:
        out["riepilogo"] = (
            f"AniList: {len(al_f)} titoli in watchlist; "
            f"aw-cli: {len(h_f)} in cronologia; "
            f"StreamingCommunity: {len(sc_items)} attività recenti"
        )
    return out


def t_watch(args: dict) -> dict:
    """Router "scegli l'opzione migliore": anime -> aw-cli (AniList), altrimenti
    film/serie -> StreamingCommunity. kind=anime|film|serie forza la scelta."""
    kind = args.get("kind")
    query = str(args["query"])
    cfg = refresh_config()

    if kind in (None, "anime"):
        try:
            p = get_provider()
            res = p.search(query)
            exact = [a for a in res if a.name.casefold() == query.casefold()]
            if kind == "anime" or exact or (len(res) > 0 and kind is None):
                anime = exact[0] if exact else res[0]
                return {"sorgente": "aw-cli (animeworld/animeunity)",
                        "scelta": anime.name,
                        "consiglio": "usare play con la stessa query per riprodurre (aggiorna AniList)",
                        "risultati_anime": [a.name for a in res[:5]]}
        except BaseException as e:
            log(f"watch anime search: {e}")

    if kind in (None, "film", "serie"):
        try:
            d = sc_call(["search", "streamingcommunity", query])
            if d.get("ok") and d.get("risultati", 0) > 0:
                top = d["anime"][0]
                return {"sorgente": "StreamingCommunity", "scelta": top["titolo"],
                        "tipo": top["tipo"], "index": 0,
                        "episodi_necessari": "serie tv: chiama sc_episodes e poi sc_stream con season/episode",
                        "risultati": [a["titolo"] for a in d["anime"][:6]]}
        except BaseException as e:
            log(f"watch sc search: {e}")

    return {"ok": False, "errore": "Nessuna fonte trovata per la query"}


# --------------------------------------------------------------------------- #
#  Registro tool (schema MCP)                                                  #
# --------------------------------------------------------------------------- #
def _prop(tp: str = "string", desc: str = "", **kw) -> dict:
    d: dict = {"type": tp, "description": desc}
    d.update(kw)
    return d

TOOLS: list[dict] = [
    {"name": "search", "description": "Cerca un anime sul provider (animeworld/animeunity). Ritorna titoli, stato e reference. Usalo per trovare il titolo esatto prima di play/info.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo o parola chiave dell'anime, es. 'one piece'"),
         "provider": _prop(desc="animeworld (default) o animeunity")},
         "required": ["query"]}},
    {"name": "latest", "description": "Ultimi episodi/colonne pubblicati dal provider. filter: a=all, s=sub, d=dub, t=tendenze.",
     "inputSchema": {"type": "object", "properties": {
         "filter": _prop(desc="a, s, d oppure t (default a)"),
         "provider": _prop(desc="animeworld o animeunity")}}},
    {"name": "info", "description": "Dettagli di un anime: trama, stato, audio, episodi totali. Cerca per titolo; usa index se la ricerca ambigua.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo dell'anime"),
         "index": _prop("integer", desc="Indice 0-based tra i risultati di search"),
         "provider": _prop()}, "required": ["query"]}},
    {"name": "episodes", "description": "Elenco episodi disponibili di un anime con progresso e completamento, e se è in cronologia.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo dell'anime"),
         "index": _prop("integer", desc="Indice tra i risultati di search"),
         "provider": _prop()}, "required": ["query"]}},
    {"name": "play", "description": "RIPRODUCE l'anime con mpv sul desktop. Senza 'episode' continua dall'ultimo visto in cronologia. Aggiorna cronologia e AniList (se configurato) in background a fine riproduzione.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo dell'anime"),
         "episode": _prop(desc="Numero episodio (es. 5, 12). Ometti per continuare"),
         "index": _prop("integer", desc="Indice tra i risultati di search"),
         "provider": _prop(),
         "private": _prop("boolean", desc="true = senza aggiornare cronologia/AniList"),
         "popup": _prop("boolean", desc="true = finestra popup piccola in basso a destra, sempre in primo piano su tutti i desktop (spostabile e ridimensionabile)")},
         "required": ["query"]}},
    {"name": "download", "description": "Scarica episodi di un anime su ~/Videos/Anime/<titolo>. Richiede episodes=[...].",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo dell'anime"),
         "episodes": _prop("array", desc="Episodi da scaricare (numeri, anche in un'unica stringa '1-12' dove supportato)"),
         "index": _prop("integer", desc="Indice tra i risultati di search"),
         "provider": _prop()}, "required": ["query", "episodes"]}},
    {"name": "offline", "description": "Elenca gli episodi già scaricati su disco (~/Videos/Anime).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "history", "description": "Cronologia di visione aw-cli: anime, episodio corrente, progresso.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "history_remove", "description": "Rimuove un anime dalla cronologia.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo esatto come in history"),
         "index": _prop("integer", desc="Indice nella cronologia")}, "required": ["query"]}},
    {"name": "anilist_list", "description": "Legge la watchlist AniList dell'utente (la lista sincronizzata: ciò che guardi nel browser con Mal-Sync appare qui). status opzionale: CURRENT, COMPLETED, PLANNING, DROPPED, PAUSED, REPEATING.",
     "inputSchema": {"type": "object", "properties": {
         "status": _prop(desc="Filtro per stato AniList"),
         "token": _prop(desc="Override token (se non configurato in aw-cli)")}}},
    {"name": "config_get", "description": "Mostra configurazione attuale di aw-cli (player, provider, anilist, cartelle).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "config_set", "description": "Aggiorna la configurazione: provider.source, player.type, player.path, general.specials, anilist.token (prende anche user_id), anilist.clear.",
     "inputSchema": {"type": "object", "properties": {
         "key": _prop(desc="provider.source | player.type | player.path | general.specials | anilist.token | anilist.clear"),
         "value": _prop(desc="Nuovo valore")}, "required": ["key", "value"]}},
    {"name": "watch", "description": "ROUTER AUTO: data una query, sceglie la fonte migliore — anime -> aw-cli (animeworld/animeunity, con sync AniList); film/serie TV -> StreamingCommunity. kind=anime|film|serie forza la scelta. Ritorna la decisione e i passi successivi.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo (film, serie TV o anime)"),
         "kind": _prop(desc="anime | film | serie (opzionale, auto se omesso)")},
         "required": ["query"]}},
    {"name": "sc_sites", "description": "Elenco dei siti supportati da StreamingCommunity tool (streamingcommunity, animeworld, crunchyroll, ...) con categoria.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "sc_search", "description": "Cerca film/serie TV su StreamingCommunity (o altro sito). Ritorna titolo, tipo (film/tv), imdb_id e index per disambiguare.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo da cercare, es. 'interstellar'"),
         "site": _prop(desc="streamingcommunity (default) o altro da sc_sites")},
         "required": ["query"]}},
    {"name": "sc_episodes", "description": "Elenco stagioni/episodi di una serie TV su StreamingCommunity (serve prima di sc_stream/sc_download per serie).",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo della serie"),
         "index": _prop("integer", desc="Indice tra i risultati di sc_search"),
         "site": _prop()}, "required": ["query"]}},
    {"name": "sc_stream", "description": "RIPRODUCE con mpv un film o episodio di serie da StreamingCommunity (proxy locale, niente pubblicità). Serie TV: serve season+episode (es. season=1 episode=3). Ritorna subito un pid; lo stato si controlla con sc_status.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo film/serie"),
         "index": _prop("integer", desc="Indice tra i risultati di sc_search"),
         "season": _prop(desc="Stagione (per serie TV)"),
         "episode": _prop(desc="Episodio o intervallo '1-3' o '*' per tutta la stagione (per serie TV)"),
         "popup": _prop("boolean", desc="true = finestra popup piccola in basso a destra, sempre in primo piano su tutti i desktop"),
         "site": _prop()}, "required": ["query"]}},
    {"name": "sc_download", "description": "Scarica film o episodi di una serie da StreamingCommunity in ~/Videos/StreamingCommunity/Film e /Serie TV. Serie: serve season+episode. Ritorna subito un pid; stato via sc_status.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo film/serie"),
         "index": _prop("integer", desc="Indice tra i risultati di sc_search"),
         "season": _prop(desc="Stagione (per serie TV)"),
         "episode": _prop(desc="Episodio o intervallo '1-3' o '*' per tutta la stagione"),
         "site": _prop()}, "required": ["query"]}},
    {"name": "sc_status", "description": "Ultime righe di log dell'helper StreamingCommunity (per monitorare stream/download in corso).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "sc_history", "description": "Cronologia dei contenuti riprodotti/scaricati da StreamingCommunity (titolo, stagione/episodio, data).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "watchlist", "description": "VISTA UNICA in tempo reale della watchlist: AniList + Simkl (browser/App: film, serie TV e anime) + cronologia aw-cli + attività StreamingCommunity. Senza query: tutta la lista. Con query: filtra per titolo e riporta a che episodio sei rimasto (prossimo_episodio). status filtra per CURRENT/COMPLETED/PLANNING/DROPPED/PAUSED/REPEATING.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Filtra per titolo (opzionale); es. 'one piece'"),
         "status": _prop(desc="Filtra per stato (opzionale) CURRENT|COMPLETED|PLANNING|...")}}},
    {"name": "simkl_list", "description": "Legge la watchlist Simkl dell'utente (film, serie TV e anime tracciati su Simkl). query filtra per titolo.",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Filtra per titolo (opzionale)")}}},
    {"name": "simkl_auth", "description": "Ricollega Simkl (OAuth2 PKCE): apre il browser, cattura il codice e salva access+refresh token (scope lettura e scrittura).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "simkl_mark", "description": "Segna come VISTO un titolo su Simkl (sync inverso da qui verso Simkl). Per serie tv indica season+episode; per anime solo episode; per film nulla. Il titolo deve essere nella watchlist Simkl (altrimenti usa simkl_id_search).",
     "inputSchema": {"type": "object", "properties": {
         "query": _prop(desc="Titolo come appare in simkl_list"),
         "season": _prop(desc="Stagione (serie tv)"),
         "episode": _prop(desc="Numero episodio guardato")}, "required": ["query"]}},
]

DISPATCH = {
    "search": t_search, "latest": t_latest, "info": t_info, "episodes": t_episodes,
    "play": t_play, "download": t_download, "offline": t_offline,
    "history": t_history, "history_remove": t_history_remove,
    "anilist_list": t_anilist_list, "config_get": t_config_get, "config_set": t_config_set,
    "watch": t_watch, "sc_sites": t_sc_sites, "sc_search": t_sc_search,
    "sc_episodes": t_sc_episodes, "sc_stream": t_sc_stream,
    "sc_download": t_sc_download, "sc_status": t_sc_status,
    "sc_history": t_sc_history, "watchlist": t_watchlist,
    "simkl_auth": t_simkl_auth, "simkl_list": t_simkl_list,
    "simkl_mark": t_simkl_mark,
}


# --------------------------------------------------------------------------- #
#  Framing JSON-RPC (MCP/stdio: newline-delimited JSON, standard attuale)      #
# --------------------------------------------------------------------------- #
def _read_message():
    """Legge un messaggio: una singola riga JSON terminata da \n."""
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        log(f"framing error: {e} on {line[:200]!r}")
        return None


def _send(obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(data + b"\n")
    sys.stdout.buffer.flush()


def _result(req_id, result) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def serve() -> None:
    log(f"aw-cli MCP server avviato (pid={os.getpid()}, aw-cli={t_config_get({})['versione']})")
    while True:
        msg = _read_message()
        if msg is None:
            break
        method = msg.get("method", "")
        rid = msg.get("id")
        is_request = rid is not None
        try:
            if method == "initialize":
                _result(rid, {"protocolVersion": "2024-11-05",
                              "capabilities": {"tools": {}},
                              "serverInfo": {"name": "aw-cli", "version": "1.0.0"}})
            elif method == "ping":
                _result(rid, {})
            elif method == "tools/list":
                _result(rid, {"tools": TOOLS})
            elif method == "tools/call":
                params = msg.get("params") or {}
                name = params.get("name")
                args = params.get("arguments") or {}
                if name not in DISPATCH:
                    _error(rid, -32602, f"Tool sconosciuto: {name}")
                    continue
                try:
                    out = DISPATCH[name](args or {})
                except BaseException as e:
                    log(f"tool {name} error: {type(e).__name__}: {e}")
                    _error(rid, -32000, f"{type(e).__name__}: {e}")
                    continue
                text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=2)
                _result(rid, {"content": [{"type": "text", "text": text}]})
            elif method == "resources/list":
                _result(rid, {"resources": []})
            elif method == "prompts/list":
                _result(rid, {"prompts": []})
            elif method.startswith("notifications/"):
                pass
            else:
                if is_request:
                    _error(rid, -32601, f"Metodo sconosciuto: {method}")
        except BaseException as e:
            log(f"protocol error: {type(e).__name__}: {e}")
            if is_request:
                try:
                    _error(rid, -32603, f"{type(e).__name__}: {e}")
                except Exception:
                    pass


if __name__ == "__main__":
    serve()

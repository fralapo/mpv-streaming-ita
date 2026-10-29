#!/usr/bin/env python3
"""
Controlla che il server MCP funzioni con le versioni installate di aw-cli e StreamingCommunity.

Avvia il server, gli parla in JSON-RPC su stdio come farebbe un agente e verifica:
  - struttura: il server parte, elenca gli strumenti, l'helper StreamingCommunity risponde;
  - rete (salvo --offline): una ricerca su aw-cli e una su StreamingCommunity trovano risultati.

Uscita: 0 tutto ok, 1 qualcosa di strutturale è rotto (aggiornamento da annullare),
2 struttura ok ma le ricerche online falliscono (spesso è il sito, non il codice).

Uso: check-mcp.py [--offline] [--python PY] [--server mcp_server.py]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()


def call(i: int, name: str, args: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}


def payload(resp: dict) -> dict:
    """Il testo JSON che lo strumento ha restituito, oppure {"errore": ...}."""
    if "error" in resp:
        return {"errore": resp["error"].get("message")}
    try:
        return json.loads(resp["result"]["content"][0]["text"])
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return {"errore": f"risposta inattesa: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="salta le ricerche online")
    ap.add_argument("--python", default=str(HOME / ".local/share/uv/tools/aw-cli/bin/python"))
    ap.add_argument("--server", default=str(HOME / ".local/share/aw-cli-tool/mcp_server.py"))
    a = ap.parse_args()

    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        call(3, "sc_sites"),
    ]
    if not a.offline:
        reqs += [call(4, "search", {"query": "frieren"}), call(5, "sc_search", {"query": "interstellar"})]

    try:
        out = subprocess.run([a.python, a.server], input="".join(json.dumps(r) + "\n" for r in reqs),
                             capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"ERRORE server MCP non avviabile: {e}")
        return 1
    resp = {}
    for line in out.stdout.splitlines():
        try:
            r = json.loads(line)
            resp[r.get("id")] = r
        except json.JSONDecodeError:
            pass

    broken, offline = [], []
    if "result" not in resp.get(1, {}):
        broken.append("il server non risponde all'avvio" + (f": {out.stderr.strip().splitlines()[-1]}" if out.stderr.strip() else ""))
    tools = {t["name"] for t in resp.get(2, {}).get("result", {}).get("tools", [])}
    missing = {"play", "watch", "sc_stream", "watchlist"} - tools
    if missing:
        broken.append(f"strumenti mancanti: {', '.join(sorted(missing))}")
    sites = payload(resp.get(3, {"error": {"message": "nessuna risposta"}}))
    if not sites.get("ok"):
        broken.append(f"helper StreamingCommunity: {sites.get('errore') or sites}")
    if not a.offline:
        for i, what in ((4, "ricerca anime (aw-cli)"), (5, "ricerca film (StreamingCommunity)")):
            p = payload(resp.get(i, {"error": {"message": "nessuna risposta"}}))
            if not p.get("risultati"):
                offline.append(f"{what}: {p.get('errore') or 'nessun risultato'}")

    for m in broken:
        print(f"ERRORE {m}")
    for m in offline:
        print(f"ATTENZIONE {m}")
    if not broken and not offline:
        print(f"OK server MCP: {len(tools)} strumenti" + ("" if a.offline else ", ricerche online funzionanti"))
    return 1 if broken else 2 if offline else 0


if __name__ == "__main__":
    sys.exit(main())

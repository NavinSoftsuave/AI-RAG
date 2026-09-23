"""Capture the RAW JSON-RPC wire exchange against the clause-search server:
initialize -> notifications/initialized -> tools/list -> tools/call.

Deliberately bypasses the mcp SDK's ClientSession for this one script and
speaks newline-delimited JSON-RPC directly over the child process's
stdin/stdout, so wire.json holds the actual bytes exchanged — not the SDK's
parsed Python objects. This is what "raw" means for requirement 4.

Run:
    ./venv/bin/python week9_deliverables/capture_wire.py
Writes:
    week9_deliverables/wire.json
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_CMD = [str(ROOT / "venv" / "bin" / "python"),
              str(ROOT / "mcp_servers" / "clause_search_server.py")]

OUT_PATH = Path(__file__).resolve().parent / "wire.json"


def send(proc, msg: dict) -> None:
    line = json.dumps(msg)
    proc.stdin.write(line + "\n")
    proc.stdin.flush()


def recv(proc) -> dict:
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("server closed stdout unexpectedly")
    return json.loads(line)


def main() -> None:
    proc = subprocess.Popen(
        SERVER_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,  # server logs/banner go here; keep stdout pure JSON-RPC
        text=True,
        bufsize=1,
        cwd=str(ROOT),
    )

    exchange = []

    # --- 1. initialize ---------------------------------------------------------
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "week9-wire-capture", "version": "0.1.0"},
        },
    }
    send(proc, init_req)
    init_resp = recv(proc)
    exchange.append({"sent": init_req, "received": init_resp})

    # --- 2. notifications/initialized (no response expected — it's a notification)
    initialized_notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    send(proc, initialized_notif)
    exchange.append({"sent": initialized_notif, "received": None})

    # --- 3. tools/list -----------------------------------------------------------
    list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    send(proc, list_req)
    list_resp = recv(proc)
    exchange.append({"sent": list_req, "received": list_resp})

    # --- 4. tools/call — a real clause lookup ------------------------------------
    call_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "get_clause",
            "arguments": {"document": "msa", "clause": "8"},
        },
    }
    send(proc, call_req)
    call_resp = recv(proc)
    exchange.append({"sent": call_req, "received": call_resp})

    proc.stdin.close()
    proc.terminate()
    proc.wait(timeout=5)

    OUT_PATH.write_text(json.dumps(exchange, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    for i, e in enumerate(exchange, start=1):
        print(f"\n--- exchange {i}: {e['sent']['method']} ---")
        print("sent:", json.dumps(e["sent"]))
        print("received:", json.dumps(e["received"]))


if __name__ == "__main__":
    main()

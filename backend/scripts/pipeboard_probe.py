"""Probe Pipeboard MCP servers to discover real tool names + response shapes.

Pipeboard exposes per-platform MCP servers (Streamable HTTP transport).
Auth = Pipeboard API token. This script:
  1. Opens an MCP session (initialize handshake).
  2. Calls tools/list to discover available tools.
  3. Optionally calls a tool (e.g. list ad accounts) to inspect response shape.

Token stays local — pass via env var, never commit it.

Usage:
    export PIPEBOARD_API_TOKEN=...        # from https://pipeboard.co/api-tokens
    python scripts/pipeboard_probe.py google-ads
    python scripts/pipeboard_probe.py meta-ads
    python scripts/pipeboard_probe.py tiktok-ads

Optionally call a discovered tool to inspect its output:
    python scripts/pipeboard_probe.py google-ads --call list-customers
    python scripts/pipeboard_probe.py google-ads --call get-campaigns --args '{"customer_id":"123"}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

import httpx

# Candidate base-URL templates. First that completes the handshake wins.
BASE_URL_TEMPLATES = [
    "https://{platform}.mcp.pipeboard.co/",
    "https://mcp.pipeboard.co/{platform}-mcp",
]


def _parse_sse_or_json(text: str) -> dict:
    """MCP streamable HTTP may answer as JSON or as SSE (data: {...}). Handle both."""
    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        return json.loads(text)
    # SSE framing: pick last `data:` line containing JSON.
    payload = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
    if payload:
        return json.loads(payload)
    raise ValueError(f"Unrecognized MCP response body:\n{text[:500]}")


def _rpc(client: httpx.Client, url: str, token: str, method: str,
         params: dict | None = None, session_id: str | None = None,
         notify: bool = False) -> tuple[dict, str | None]:
    """Send one JSON-RPC message. Returns (parsed_body, mcp_session_id_header)."""
    body = {"jsonrpc": "2.0", "method": method}
    if not notify:
        body["id"] = str(uuid.uuid4())
    if params is not None:
        body["params"] = params

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        # Streamable HTTP servers require client to accept SSE.
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    resp = client.post(url, params={"token": token}, json=body, headers=headers)
    sid = resp.headers.get("Mcp-Session-Id")
    if notify:
        return {}, sid
    resp.raise_for_status()
    return _parse_sse_or_json(resp.text), sid


def open_session(client: httpx.Client, url: str, token: str) -> str | None:
    """Run MCP initialize handshake. Returns session id (or None if server is stateless)."""
    init_params = {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "tahinis-probe", "version": "0.1.0"},
    }
    result, sid = _rpc(client, url, token, "initialize", init_params)
    if "error" in result:
        raise RuntimeError(f"initialize error: {result['error']}")
    # Confirm initialized (notification, no id).
    _rpc(client, url, token, "notifications/initialized", {}, session_id=sid, notify=True)
    return sid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("platform", help="google-ads | meta-ads | tiktok-ads | snap-ads | reddit-ads")
    ap.add_argument("--call", help="Tool name to invoke after discovery")
    ap.add_argument("--args", default="{}", help="JSON args for --call tool")
    args = ap.parse_args()

    token = os.getenv("PIPEBOARD_API_TOKEN")
    if not token:
        print("ERROR: set PIPEBOARD_API_TOKEN env var (https://pipeboard.co/api-tokens)", file=sys.stderr)
        return 1

    last_err = None
    with httpx.Client(timeout=60) as client:
        for tmpl in BASE_URL_TEMPLATES:
            url = tmpl.format(platform=args.platform)
            try:
                print(f"\n=== Trying {url} ===")
                sid = open_session(client, url, token)
                print(f"  handshake OK (session_id={sid})")

                tools, _ = _rpc(client, url, token, "tools/list", {}, session_id=sid)
                tool_list = tools.get("result", {}).get("tools", [])
                print(f"\n  {len(tool_list)} tools discovered:")
                for t in tool_list:
                    name = t.get("name")
                    desc = (t.get("description") or "").split("\n")[0][:80]
                    schema = t.get("inputSchema", {}).get("properties", {})
                    print(f"    - {name}({', '.join(schema.keys())}) — {desc}")

                if args.call:
                    print(f"\n  Calling {args.call}({args.args}) ...")
                    call_params = {"name": args.call, "arguments": json.loads(args.args)}
                    out, _ = _rpc(client, url, token, "tools/call", call_params, session_id=sid)
                    print(json.dumps(out, indent=2)[:4000])

                print(f"\nWORKING BASE URL: {url}")
                return 0
            except Exception as e:  # try next template
                last_err = e
                print(f"  failed: {e}")

    print(f"\nAll base URLs failed. Last error: {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

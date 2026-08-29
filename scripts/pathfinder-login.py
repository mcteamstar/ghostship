#!/usr/bin/env python3
"""Obtain a Migration Pathfinder refresh token for the transport's MCP proxy.

Pathfinder's MCP server authenticates with Cognito tokens issued through a
browser OAuth flow, which a headless crew container cannot complete. Transport
holds the credential on the crew's behalf (see docs/migration-assess.md), so it
needs a refresh token on disk once. This runs that flow.

Run it on a machine with a browser:

    python3 scripts/pathfinder-login.py \\
        --origin https://pathfinder.staging.sca.versent.io \\
        --client-id <cognito app client id>

It discovers the OAuth endpoints from the origin, runs an authorization-code
flow with PKCE against a loopback redirect, and writes the refresh token to the
transport's data directory with mode 600. Tokens are never printed, logged, or
passed on a command line — the exchange happens in-process and the value goes
straight to the file.

After it succeeds, add the printed GA_PATHFINDER_* settings to your ghostship
config and re-run install.sh so transport picks them up.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import platform
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

DEFAULT_SCOPE = "mcp/access"


def default_data_dir() -> Path:
    """Where install.sh puts the transport's data directory on this platform."""
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "ghost-academy" / "data"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "ghost-academy" / "data"


def discover(origin: str) -> dict:
    url = origin.rstrip("/") + "/.well-known/oauth-authorization-server"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.load(resp)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Loopback receiver for the authorization code.

    Serves until a request actually carries `code` or `error`. A single-shot
    handler is not enough: browsers routinely fire /favicon.ico at a loopback
    redirect target, and that request would otherwise consume the one slot and
    strand the flow.
    """

    result: dict = {}

    def do_GET(self) -> None:
        query = urllib.parse.urlparse(self.path).query
        params = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}
        if "code" not in params and "error" not in params:
            # Not the redirect (favicon, a stray probe) — answer and keep waiting.
            self.send_response(204)
            self.end_headers()
            return
        _CallbackHandler.result = params
        ok = "code" in params
        body = (
            b"<html><body><h2>Pathfinder login complete.</h2>"
            b"<p>You can close this tab and return to the terminal.</p></body></html>"
            if ok else
            b"<html><body><h2>Login failed.</h2><p>See the terminal.</p></body></html>"
        )
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # noqa: D102 - silence access logging
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origin", required=True,
                    help="Pathfinder origin, e.g. https://pathfinder.staging.sca.versent.io")
    ap.add_argument("--client-id", required=True, help="Cognito app client id")
    ap.add_argument("--callback-port", type=int, default=8080,
                    help="Loopback port for the OAuth redirect (default 8080). Must be "
                         "registered as a callback URL on the Cognito app client.")
    ap.add_argument("--scope", default=DEFAULT_SCOPE)
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="Transport data directory (default: this platform's install location)")
    args = ap.parse_args()

    data_dir = args.data_dir or default_data_dir()
    if not data_dir.is_dir():
        print(f"✗ Data directory not found: {data_dir}", file=sys.stderr)
        print("  Run install.sh first, or pass --data-dir.", file=sys.stderr)
        return 1

    print(f"Discovering OAuth endpoints from {args.origin} ...")
    try:
        meta = discover(args.origin)
    except Exception as e:
        print(f"✗ Could not read OAuth metadata: {e}", file=sys.stderr)
        return 1
    authorize_url = meta["authorization_endpoint"]
    token_url = meta["token_endpoint"]
    print(f"  authorize: {authorize_url}")
    print(f"  token:     {token_url}")

    # PKCE. token_endpoint_auth_method is "none" (public client), so the code
    # verifier is the only thing binding the exchange to this process.
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    redirect_uri = f"http://localhost:{args.callback_port}/callback"

    try:
        server = http.server.HTTPServer(("127.0.0.1", args.callback_port), _CallbackHandler)
    except OSError as e:
        print(f"✗ Cannot listen on port {args.callback_port}: {e}", file=sys.stderr)
        print("  Another process may be holding it (a previous run, or an MCP client).",
              file=sys.stderr)
        return 1

    done = threading.Event()

    def _serve() -> None:
        while not _CallbackHandler.result:
            server.handle_request()
        done.set()

    threading.Thread(target=_serve, daemon=True).start()

    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "scope": args.scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    url = f"{authorize_url}?{params}"
    print(f"\nOpening your browser to sign in. If it does not open, visit:\n{url}\n")
    webbrowser.open(url)

    print(f"Waiting for the redirect on {redirect_uri} ...")
    if not done.wait(timeout=300):
        print("✗ Timed out after 5 minutes waiting for the browser redirect.", file=sys.stderr)
        return 1

    result = _CallbackHandler.result
    if "error" in result:
        description = result.get("error_description", "")
        print(f"✗ Authorization failed: {result.get('error')} {description}",
              file=sys.stderr)
        if "Account linked" in description or "sign in again" in description.lower():
            # Cognito's PreSignUp trigger links a federated identity to an
            # existing user on first sign-in and rejects that same attempt. The
            # link now exists, so a second run goes through.
            print("\n  This is Cognito's account-linking trigger, which fires once and "
                  "\n  rejects the sign-in that caused it. The link is now in place — "
                  "\n  run this command again and it should complete.", file=sys.stderr)
        return 1
    if result.get("state") != state:
        print("✗ State mismatch — aborting rather than trusting this redirect.", file=sys.stderr)
        return 1

    print("Exchanging the authorization code for tokens ...")
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": args.client_id,
        "code": result["code"],
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(
        token_url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            tokens = json.load(resp)
    except urllib.error.HTTPError as e:
        # The body can echo the code back, so report status only.
        print(f"✗ Token exchange failed with HTTP {e.code}.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"✗ Token exchange failed: {type(e).__name__}", file=sys.stderr)
        return 1

    refresh = tokens.get("refresh_token")
    if not refresh:
        print("✗ No refresh_token returned. Check the app client allows the "
              "refresh_token grant.", file=sys.stderr)
        return 1

    target = data_dir / "ga-pathfinder-refresh"
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(refresh)

    print(f"\n✓ Refresh token written to {target} (mode 600)")
    print(f"  access token lifetime: {tokens.get('expires_in', 'unknown')}s "
          f"(transport refreshes it automatically)")
    print("\nAdd these to your ghostship config, then re-run install.sh:\n")
    print(f'  GA_PATHFINDER_URL="{args.origin.rstrip("/")}"')
    print(f'  GA_PATHFINDER_TOKEN_URL="{token_url}"')
    print(f'  GA_PATHFINDER_CLIENT_ID="{args.client_id}"')
    print('  GA_PATHFINDER_ACCESS_TOKEN=""   # leave empty: the refresh token is better')
    return 0


if __name__ == "__main__":
    sys.exit(main())

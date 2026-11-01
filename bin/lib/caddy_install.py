#!/usr/bin/env python3
"""caddy_install.py — Generate Caddy initial-config.json for Ghost Academy.

Replaces the Caddy JSON heredoc in bin/install.sh.  Produces the full
initial-config.json as a Python dict serialised with json.dumps; no
string interpolation.

Usage (CLI):
    python3 bin/lib/caddy_install.py --output <path>

All config is read from environment variables when running as a CLI entry
point (mirroring install.sh's resolved environment).
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Portal-token header injected on every upstream request.
# Caddy reads the secret from the mounted Podman secret file.
_PORTAL_TOKEN_HEADER = {
    "headers": {
        "request": {
            "set": {
                "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]
            }
        }
    }
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class CaddyConfig:
    """All fields needed to render initial-config.json."""

    port: str = "64057"
    tls_mode: str = "off"        # off | internal | tailscale | acme
    acme_domain: str = ""        # required when tls_mode == "acme"
    ga_api_key: str = ""         # non-empty → gated routes + 401 handler


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate_caddy_config(config: CaddyConfig) -> dict:
    """Return the initial-config.json structure as a Python dict."""

    listen = f":{config.port}"

    # --- TLS stanza and automatic_https ---
    tls_mode = config.tls_mode or "off"
    auto_https: dict | None = None
    tls_stanza: dict

    if tls_mode == "off":
        tls_stanza = {}
        auto_https = {"disable": True}
    elif tls_mode == "tailscale":
        tls_stanza = {
            "automation": {
                "policies": [
                    {"get_certificate": [{"via": "tailscale"}]}
                ]
            }
        }
    elif tls_mode == "acme":
        tls_stanza = {
            "automation": {
                "policies": [
                    {
                        "subjects": [config.acme_domain],
                        "issuers": [{"module": "acme"}],
                    }
                ]
            }
        }
    else:
        # "internal" or any unrecognised value → internal CA
        tls_stanza = {
            "automation": {
                "policies": [
                    {"issuers": [{"module": "internal"}]}
                ]
            }
        }

    # --- Auth routes (gated vs passthrough) ---
    if config.ga_api_key:
        auth_routes = _gated_auth_routes()
    else:
        auth_routes = _passthrough_auth_routes()

    # --- Radar route ---
    if config.ga_api_key:
        radar_route = _gated_radar_route()
    else:
        radar_route = _passthrough_radar_route()

    # --- Misc route ---
    misc_route = {
        "@id": "ga-transport-misc",
        "match": [
            {
                "path": [
                    "/health",
                    "/version",
                    "/openapi.json",
                    "/dashboard/*",
                    "/login",
                    "/login*",
                    "/logout",
                    "/logout*",
                    "/crews/*/captain/stop",
                ]
            }
        ],
        "handle": [
            {
                "handler": "reverse_proxy",
                "upstreams": [{"dial": "ga-transport:64057"}],
                **_PORTAL_TOKEN_HEADER,
            }
        ],
    }

    routes = auth_routes + [radar_route, misc_route]

    # --- Main server ---
    main_server: dict = {
        "listen": [listen],
        "routes": routes,
    }
    if auto_https is not None:
        main_server["automatic_https"] = auto_https

    doc: dict = {
        "admin": {"listen": "0.0.0.0:2019"},
        "apps": {
            "http": {
                "servers": {
                    "ga-main": main_server,
                }
            },
            "tls": tls_stanza,
        },
    }

    return doc


# ---------------------------------------------------------------------------
# Route builders
# ---------------------------------------------------------------------------

def _gated_auth_routes() -> list[dict]:
    """Bearer-gated MCP/files routes + 401 handler when GA_API_KEY is set."""
    return [
        {
            "@id": "ga-transport-mcp",
            "match": [
                {
                    "path": ["/mcp*"],
                    "header": {
                        "Authorization": [
                            "Bearer {file./run/secrets/ga-api-key}"
                        ]
                    },
                }
            ],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": "ga-transport:64057"}],
                    **_PORTAL_TOKEN_HEADER,
                }
            ],
        },
        {
            "@id": "ga-transport-files-presigned",
            "match": [
                {
                    "path": ["/files/*"],
                    "query": {"sig": ["*"]},
                }
            ],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": "ga-transport:64057"}],
                    **_PORTAL_TOKEN_HEADER,
                }
            ],
        },
        {
            "@id": "ga-transport-files",
            "match": [
                {
                    "path": ["/files/*"],
                    "header": {
                        "Authorization": [
                            "Bearer {file./run/secrets/ga-api-key}"
                        ]
                    },
                }
            ],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": "ga-transport:64057"}],
                    **_PORTAL_TOKEN_HEADER,
                }
            ],
        },
        {
            "@id": "ga-mcp-files-reject",
            "match": [{"path": ["/mcp*", "/files/*"]}],
            "handle": [
                {
                    "handler": "static_response",
                    "status_code": 401,
                    "headers": {"Www-Authenticate": ["Bearer"]},
                    "body": "Unauthorized",
                }
            ],
        },
    ]


def _passthrough_auth_routes() -> list[dict]:
    """Open passthrough routes when no GA_API_KEY (Tailscale-gated)."""
    return [
        {
            "@id": "ga-transport-mcp",
            "match": [{"path": ["/mcp*"]}],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": "ga-transport:64057"}],
                    **_PORTAL_TOKEN_HEADER,
                }
            ],
        },
        {
            "@id": "ga-transport-files",
            "match": [{"path": ["/files/*"]}],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": "ga-transport:64057"}],
                    **_PORTAL_TOKEN_HEADER,
                }
            ],
        },
    ]


def _gated_radar_route() -> dict:
    """Session-gated Radar route (forward-auth via reverse_proxy)."""
    return {
        "@id": "ga-radar",
        "match": [
            {
                "path": [
                    "/",
                    "/api/crews",
                    "/api/crews/*",
                    "/static/*",
                ]
            }
        ],
        "handle": [
            {
                "handler": "reverse_proxy",
                "upstreams": [{"dial": "ga-transport:64057"}],
                "rewrite": {"method": "GET", "uri": "/dashboard/auth"},
                "headers": {
                    "request": {
                        "set": {
                            "X-Forwarded-Method": ["{http.request.method}"],
                            "X-Forwarded-Uri": ["{http.request.uri}"],
                            "X-Transport-Token": [
                                "{file./run/secrets/ga-transport-secret}"
                            ],
                        }
                    }
                },
                "handle_response": [
                    {
                        "match": {"status_code": [2]},
                        "routes": [{"handle": [{"handler": "vars"}]}],
                    },
                    {
                        "match": {"status_code": [4]},
                        "routes": [
                            {
                                "handle": [
                                    {
                                        "handler": "static_response",
                                        "status_code": 302,
                                        "headers": {
                                            "Location": [
                                                "/dashboard/login?next={http.request.uri}"
                                            ]
                                        },
                                    }
                                ]
                            }
                        ],
                    },
                ],
            },
            {
                "handler": "reverse_proxy",
                "upstreams": [{"dial": "ga-radar:8080"}],
                **_PORTAL_TOKEN_HEADER,
            },
        ],
    }


def _passthrough_radar_route() -> dict:
    """Open passthrough Radar route (Tailscale-gated install)."""
    return {
        "@id": "ga-radar",
        "match": [
            {
                "path": [
                    "/",
                    "/api/crews",
                    "/api/crews/*",
                    "/static/*",
                ]
            }
        ],
        "handle": [
            {
                "handler": "reverse_proxy",
                "upstreams": [{"dial": "ga-radar:8080"}],
                **_PORTAL_TOKEN_HEADER,
            }
        ],
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _config_from_env() -> CaddyConfig:
    """Build a CaddyConfig from the current environment."""
    env = os.environ
    return CaddyConfig(
        port=env.get("PORT", "64057"),
        tls_mode=env.get("GA_PORTAL_TLS_MODE", "off"),
        acme_domain=env.get("GA_PORTAL_DOMAIN", ""),
        ga_api_key=env.get("GA_API_KEY", ""),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Caddy initial-config.json for Ghost Academy"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the generated initial-config.json",
    )
    args = parser.parse_args()

    config = _config_from_env()
    doc = generate_caddy_config(config)
    content = json.dumps(doc, indent=2)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    out.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"✓ Caddy initial-config.json written to {out}")


if __name__ == "__main__":
    main()

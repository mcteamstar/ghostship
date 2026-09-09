"""Canonical container-side infrastructure constants (TRN-142).

A zero-dependency leaf module: the single home for the infrastructure
constants that were previously duplicated across lifecycle.py, server.py,
podman.py, captain.py, and monitors.py.

This module MUST NOT import from any other ``transport.*`` module. Its purpose
is to be safe to import from anywhere in the transport package — including
podman.py and captain.py, which cannot import lifecycle.py without creating a
load-time cycle — without dragging in a heavyweight module just to reach a
plain integer or string constant.

Config fields and env-var names deliberately do NOT live here; they belong in
config.py. See openspec/changes/trn-142-constants-and-lazy-import-cleanup/.
"""

from __future__ import annotations

# ── Crew gateway ──────────────────────────────────────────────────────────────
# KiroCrew gateway port — fixed by upstream, not configurable from this transport.
CREW_GATEWAY_PORT = 5476

# ── Container / volume naming prefixes ────────────────────────────────────────
CREW_CONTAINER_PREFIX = "gs-"
CREW_VOLUME_PREFIX = "gs-vol-"
CREW_HOME_VOLUME_PREFIX = "gs-home-"

# ── Podman networks ───────────────────────────────────────────────────────────
GA_PORTSIDE_NETWORK = "ga-portside"
GA_STARBOARD_NETWORK = "ga-starboard"

# ── Worker personas ───────────────────────────────────────────────────────────
PERSONA_NAMES = ("ghost", "spectre", "banshee", "wraith", "reaper", "raven")

# ── Container-side helper scripts ─────────────────────────────────────────────
# Helper scripts baked into the crew image at /scripts/ by the Containerfile
# (see transport/container_scripts/, TRN-74).
SCRIPTS_DIR = "/scripts"

"""Crew — the data class modelling one crew's registry entry.

A ``Crew`` instance is the typed, self-describing counterpart to the raw dict
stored under ``crews[crew_id]`` in ``crews.json``. ``to_dict`` / ``from_dict``
preserve that JSON shape exactly (TRN-240 invariant: no serialisation change),
so the registry file is byte-compatible across the migration.

Design notes (see openspec/changes/trn-240-transport-refactor/design.md):
- ``crew_id`` is carried explicitly on the object even though it is the dict
  KEY in the registry — this keeps the object self-describing when passed around.
- ``warm_until`` is in-memory only (D2): it is NOT serialised by ``to_dict`` and
  is initialised to ``0.0`` by ``from_dict``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# The crew gateway port is effectively constant (CREW_GATEWAY_PORT = 5476).
CREW_GATEWAY_PORT = 5476


@dataclass
class Crew:
    """One crew's registry entry.

    Field defaults mirror the behaviour of the raw-dict call sites that used
    ``crew.get("<key>", <default>)``.
    """

    crew_id: str
    container: str
    volume: str
    home_volume: str
    port: int = CREW_GATEWAY_PORT
    cookie: str = ""
    internal_cookie: str = ""
    status: str = "stopped"
    composition: str = "spec-ops"
    acp_backend: str = "kiro"
    created_at: str = ""
    last_used: float = 0.0
    # In-memory only — the ACP prewarm marker. Excluded from to_dict (D2).
    warm_until: float = 0.0
    enrolled_agents: list[str] = field(default_factory=list)
    admiral_secret_id: str = ""
    policy_version: str = ""
    policy_signing_key_id: str = ""
    crew_image_version: str = "unknown"
    schedules: list[dict] = field(default_factory=list)
    batches: list[dict] = field(default_factory=list)

    # ── computed / view methods ───────────────────────────────────────────────

    def gateway_url(self) -> str:
        """The crew gateway base URL."""
        return f"http://{self.container}:{self.port}"

    def cookie_header(self) -> str:
        """The ``mc_token_<port>=<value>`` cookie value (not the full header)."""
        return f"mc_token_{self.port}={self.cookie}"

    def is_idle(self, timeout_secs: int) -> bool:
        """True when ``last_used`` is set and older than ``timeout_secs``."""
        return self.last_used > 0 and (time.time() - self.last_used) > timeout_secs

    def is_warm(self) -> bool:
        """True when a fresh ACP prewarm marker is set."""
        return time.monotonic() < self.warm_until

    # ── serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialise for ``crews.json``.

        Produces the same keys/values as the ``crew_entry`` dict built in
        ``_finish_crew_setup``: the always-present keys first, then the
        conditionally-present keys (``internal_cookie``, ``policy_version``,
        ``policy_signing_key_id``) only when truthy, and ``schedules`` /
        ``batches`` only when non-empty. ``warm_until`` is never serialised.
        ``crew_id`` is the dict KEY in the registry, so it is not part of the
        value here.
        """
        d: dict = {
            "container": self.container,
            "volume": self.volume,
            "home_volume": self.home_volume,
            "port": self.port,
            "cookie": self.cookie,
            "status": self.status,
            "composition": self.composition,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "admiral_secret_id": self.admiral_secret_id,
            "crew_image_version": self.crew_image_version,
            "acp_backend": self.acp_backend,
            "enrolled_agents": list(self.enrolled_agents),
        }
        if self.internal_cookie:
            d["internal_cookie"] = self.internal_cookie
        if self.policy_version:
            d["policy_version"] = self.policy_version
            d["policy_signing_key_id"] = self.policy_signing_key_id
        if self.schedules:
            d["schedules"] = self.schedules
        if self.batches:
            d["batches"] = self.batches
        return d

    @classmethod
    def from_dict(cls, crew_id: str, d: dict) -> "Crew":
        """Deserialise from a ``crews.json`` entry.

        Unknown keys are ignored; missing keys fall back to the dataclass
        defaults, matching the ``crew.get("<key>", <default>)`` semantics of the
        raw-dict call sites. ``warm_until`` is always initialised to ``0.0`` — it
        is never read from JSON (D2).
        """
        return cls(
            crew_id=crew_id,
            container=d.get("container", ""),
            volume=d.get("volume", ""),
            home_volume=d.get("home_volume", ""),
            port=d.get("port", CREW_GATEWAY_PORT),
            cookie=d.get("cookie", ""),
            internal_cookie=d.get("internal_cookie", ""),
            status=d.get("status", "stopped"),
            composition=d.get("composition", "spec-ops"),
            acp_backend=d.get("acp_backend", "kiro"),
            created_at=d.get("created_at", ""),
            last_used=d.get("last_used", 0.0),
            warm_until=0.0,
            enrolled_agents=list(d.get("enrolled_agents", [])),
            admiral_secret_id=d.get("admiral_secret_id", ""),
            policy_version=d.get("policy_version", ""),
            policy_signing_key_id=d.get("policy_signing_key_id", ""),
            crew_image_version=d.get("crew_image_version", "unknown"),
            schedules=list(d.get("schedules", [])),
            batches=list(d.get("batches", [])),
        )

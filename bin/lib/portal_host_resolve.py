#!/usr/bin/env python3
"""portal_host_resolve.py — Shell helper for API-key resolution.

Called by install.sh to resolve the endpoint API key and emit
shell-safe KEY=value lines that can be eval'd back into the
calling environment. This pattern is transitional — Phase 6
(install_main.py) eliminates it by importing portal_host directly.

Environment variables read:
    DATA_DIR, API_KEY_FLAG_PASSED, _FLAG_API_KEY, GA_API_KEY,
    GA_API_KEY_DISABLED, GA_API_KEY_SOURCE, GA_API_KEY_DEPRECATED_OFF,
    _GHOSTSHIP_DIR (used to locate portal_host.py)

Stdout: one line per resolved key, e.g.:
    GA_API_KEY=resolved-key
    GA_API_KEY_DISABLED=
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Locate portal_host.py via _GHOSTSHIP_DIR
_ghostship = os.environ.get("_GHOSTSHIP_DIR", "")
if _ghostship:
    _lib = Path(_ghostship) / "bin" / "lib"
    if str(_lib) not in sys.path:
        sys.path.insert(0, str(_lib))

from portal_host import resolve_api_key  # noqa: E402

env = os.environ
result = resolve_api_key(
    env.get("DATA_DIR", ""),
    api_key_flag_passed=(env.get("API_KEY_FLAG_PASSED", "0") == "1"),
    flag_api_key=env.get("_FLAG_API_KEY", ""),
    ga_api_key=env.get("GA_API_KEY", ""),
    ga_api_key_disabled=env.get("GA_API_KEY_DISABLED", ""),
    ga_api_key_source=env.get("GA_API_KEY_SOURCE", ""),
    ga_api_key_deprecated_off=env.get("GA_API_KEY_DEPRECATED_OFF", ""),
)

# Emit shell-safe assignments. Values contain no newlines (keys are hex/empty).
print(f"GA_API_KEY={result['ga_api_key']}")
print(f"GA_API_KEY_DISABLED={result['ga_api_key_disabled']}")

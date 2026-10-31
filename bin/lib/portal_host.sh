#!/usr/bin/env bash
# DEPRECATED: portal_host.sh — now a one-line delegator to portal_host.py.
# All logic lives in bin/lib/portal_host.py; this file is kept only for
# callers that source it directly (e.g. tests/unit/test_portal_host.py).
# Sourcing callers that invoke the shell functions directly need to switch to
# calling the Python module.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/portal_host.py" "$@"

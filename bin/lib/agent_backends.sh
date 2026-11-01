#!/usr/bin/env bash
# DEPRECATED: agent_backends.sh — now a one-line delegator to agent_backends.py.
# All logic lives in bin/lib/agent_backends.py; this file is kept only for
# callers that source it directly (e.g. tests/unit/test_install.py static checks).
# Sourcing callers that invoke the shell functions directly need to switch to
# calling the Python module.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/agent_backends.py" "$@"

#!/usr/bin/env python3
"""Security CI checks for TRN-70 (secrets-management 1.4, input-validation 4.4).

Two shift-left gates that fail the build on a regression:

1. Secret scan — flags likely committed live secrets (private keys, AWS keys,
   long hex/base64 tokens assigned to secret-looking names). Heuristic and
   intentionally conservative; example/placeholder values are ignored.

2. Unsafe-query check — flags SQL built by string concatenation or f-string
   interpolation of a variable directly into a query, which the
   injection-safe-data-access requirement forbids (use bound parameters).

Exit non-zero on any finding. Run from the repo root: python3 tests/security_scan.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Directories/files never scanned (fixtures, docs, this scanner, VCS).
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".github"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".lock"}

# Placeholder markers that make a match a non-secret by construction.
PLACEHOLDER_RE = re.compile(
    r"(?i)(example|placeholder|dummy|fixture|test[-_]|[-_]test|your[-_]?|xxx+|<[^>]+>|"
    r"changeme|redacted|fixed[-_]|fake|sample|\$\{|token_hex|token_urlsafe)"
)

SECRET_PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "hardcoded secret assignment",
        re.compile(
            r"""(?ix)
            (password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key|
             client[_-]?secret|auth[_-]?token)
            \s*[:=]\s*
            ['"][A-Za-z0-9+/=_\-]{16,}['"]
            """
        ),
    ),
]

# f"...{var}..." or "..." + var inside a SQL keyword context.
SQL_KEYWORDS = r"(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|WHERE|VALUES)"
UNSAFE_QUERY_PATTERNS = [
    (
        "f-string interpolation into SQL",
        re.compile(rf"""(?is)f['"][^'"]*{SQL_KEYWORDS}[^'"]*\{{[^}}]+\}}"""),
    ),
    (
        "string concatenation into SQL",
        re.compile(rf"""(?is)['"][^'"]*{SQL_KEYWORDS}[^'"]*['"]\s*\+\s*\w"""),
    ),
]


def _iter_files():
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        # Skip the scanner and the security tests (they contain sample patterns).
        rel = path.relative_to(REPO).as_posix()
        if rel in ("tests/security_scan.py", "tests/unit/test_trn70_security.py"):
            continue
        yield path


def scan_secrets() -> list[str]:
    findings = []
    for path in _iter_files():
        # Test fixtures legitimately contain fake credential strings; the secret
        # scan targets production/committed config, not the test tree.
        if path.relative_to(REPO).as_posix().startswith("tests/"):
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if PLACEHOLDER_RE.search(line):
                continue
            for label, pat in SECRET_PATTERNS:
                if pat.search(line):
                    rel = path.relative_to(REPO).as_posix()
                    findings.append(f"{rel}:{lineno}: possible {label}")
    return findings


def scan_unsafe_queries() -> list[str]:
    findings = []
    for path in _iter_files():
        if path.suffix != ".py":
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        for label, pat in UNSAFE_QUERY_PATTERNS:
            for m in pat.finditer(text):
                # Allow interpolation of an all-caps constant (table/db name),
                # which is not untrusted input.
                snippet = m.group(0)
                interpolated = re.search(r"\{([^}]+)\}", snippet)
                if interpolated and re.fullmatch(r"[A-Z0-9_]+", interpolated.group(1).strip()):
                    continue
                lineno = text[: m.start()].count("\n") + 1
                rel = path.relative_to(REPO).as_posix()
                findings.append(f"{rel}:{lineno}: {label}")
    return findings


def main() -> int:
    secret_findings = scan_secrets()
    query_findings = scan_unsafe_queries()

    if secret_findings:
        print("✗ Secret scan found potential committed secrets:")
        for f in secret_findings:
            print(f"    {f}")
    else:
        print("✓ Secret scan: no committed live secrets detected.")

    if query_findings:
        print("✗ Unsafe-query check found string-built SQL:")
        for f in query_findings:
            print(f"    {f}")
    else:
        print("✓ Unsafe-query check: no string-concatenated SQL detected.")

    return 1 if (secret_findings or query_findings) else 0


if __name__ == "__main__":
    sys.exit(main())

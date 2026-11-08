#!/usr/bin/env python3
"""Read-only dependency inventory validation and manual upstream review."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config" / "dependencies.yaml"
TIMEOUT_SECS = 5
MAX_LOOKUPS = 64
USER_AGENT = "GhostshipDependencyReview/1.0"
SCAN_EXCLUDED_PARTS = {".git", "tests", "vendor", ".venv", "venv", "node_modules", ".tox", "__pycache__"}

try:
    import yaml
except ImportError:  # Local offline use does not require installing PyYAML.
    sys.path.insert(0, str(ROOT / "bin" / "lib" / "vendor"))
    import yaml


def load_inventory(path: Path = INVENTORY) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("components"), list):
        raise ValueError("inventory must contain a components list")
    return data


def relpath(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def norm_package(value: str) -> str:
    name, _, extras = value.partition("[")
    name = re.sub(r"[-_.]+", "-", name).lower()
    return f"{name}[{extras.lower()}" if extras else name


def requirement_entries(text: str) -> dict[str, str]:
    found = {}
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+(?:\[[^\]]+\])?)\s*(.*)$", line)
        if match:
            found[norm_package(match.group(1))] = match.group(2).strip()
    return found


def image_name(reference: str) -> str:
    image = reference.split("@", 1)[0]
    last = image.rsplit("/", 1)[-1]
    return last.split(":", 1)[0]


def key_for(kind: str, path: str, name: str = "") -> str:
    return f"{kind}:{path}:{name}" if name else f"{kind}:{path}"


def classify_declaration(kind: str, value) -> str:
    """Describe source syntax without treating it as an installed resolution."""
    if kind == "requirement":
        return "range" if re.search(r"(?:^|,)\s*(?:~=|!=|>=|<=|>|<)", str(value)) else "exact constraint"
    if kind == "git_ref":
        ref = value.get("ref", "") if isinstance(value, dict) else str(value)
        return "commit ref" if re.fullmatch(r"[0-9a-fA-F]{40}", ref) else "branch or tag ref"
    if kind in {"container_from", "image_arg", "python_image_default", "compose_image"}:
        return "digest" if "@sha256:" in str(value) else "image tag"
    if kind == "npm":
        return "exact package constraint"
    if kind == "github_python_runtime":
        return "requested runtime stream"
    return "declared input"


def _set(out: dict, kind: str, path: str, name: str, value) -> None:
    out[key_for(kind, path, name)] = value


def _apt_packages(text: str) -> list[str]:
    flattened = re.sub(r"\\\s*\n", " ", text)
    result = set()
    for match in re.finditer(r"apt-get\s+install\b(.*?)(?:&&|;|$)", flattened, re.S):
        for token in shlex.split(match.group(1)):
            if not token.startswith("-") and re.fullmatch(r"[A-Za-z0-9.+:-]+", token):
                result.add(token)
    return sorted(result)


def discover_inputs(root: Path) -> dict[str, object]:
    """Extract declaration keys and values from supported authoritative files."""
    found: dict[str, object] = {}
    for path in sorted(root.rglob("*requirements*.txt")):
        parts = path.relative_to(root).parts
        if any(part in SCAN_EXCLUDED_PARTS for part in parts):
            continue
        rel = relpath(root, path)
        for package, constraint in requirement_entries(path.read_text(encoding="utf-8")).items():
            _set(found, "requirement", rel, package, constraint)

    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if any(part in SCAN_EXCLUDED_PARTS for part in parts):
            continue
        if not path.is_file() or (path.name != "Containerfile" and path.suffix not in {".sh", ".py"}):
            continue
        rel = relpath(root, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"\bnpm\s+install\s+-g\s+(@[^/\s]+/[^@\s]+|[^@\s]+)@([^\s;\\]+)", text):
            _set(found, "npm", rel, match.group(1), match.group(2))
        if path.name == "Containerfile":
            for match in re.finditer(r"\bpip3?\s+install\b[^\n]*?['\"]?([A-Za-z0-9_.-]+)(==|~=|!=|<=|>=|<|>)([^\s'\"]+)", text):
                _set(found, "pip_install", rel, norm_package(match.group(1)), match.group(2) + match.group(3))

        if path.name == "Containerfile":
            for match in re.finditer(r"^\s*FROM\s+([^\s]+)", text, re.M):
                reference = match.group(1)
                if not reference.startswith(("localhost/", "${")):
                    _set(found, "container_from", rel, image_name(reference), reference)
            for match in re.finditer(r"^\s*ARG\s+([A-Z0-9_]*IMAGE)=([^\s]+)", text, re.M):
                arg, reference = match.groups()
                if not reference.startswith(("localhost/", "${")):
                    _set(found, "image_arg", rel, arg, reference.strip('"'))
            apt = _apt_packages(text)
            if apt:
                _set(found, "apt_group", rel, "", apt)
            url = re.search(r"https://deb\.nodesource\.com/setup_(\d+)\.x", text)
            checksum = re.search(r"NODESOURCE_SETUP_SHA256=\"?([a-fA-F0-9]{64})", text)
            if url and checksum:
                _set(found, "node_setup", rel, "nodejs-" + url.group(1), {
                    "major": int(url.group(1)), "sha256": checksum.group(1).lower(),
                    "url": f"https://deb.nodesource.com/setup_{url.group(1)}.x",
                })
            agents_url = re.search(r'^\s*ARG\s+AGENTS_URL="?([^\s"#]+)', text, re.M)
            agents_ref = re.search(r'^\s*ARG\s+AGENTS_REF="?([^\s"#]+)', text, re.M)
            if agents_url and agents_ref:
                _set(found, "git_ref", rel, "shared-agent-assets", {
                    "url": agents_url.group(1), "ref": agents_ref.group(1),
                })

        if path.suffix == ".py" and path.name == "config.py":
            match = re.search(r'kc_base_image\s*:\s*str\s*=\s*["\']([^"\']+)', text)
            if match:
                _set(found, "python_image_default", rel, "kc_base_image", match.group(1))

    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        rel = relpath(root, path)
        workflow = path.read_text(encoding="utf-8")
        for name, ref in re.findall(r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)", workflow, re.M):
            _set(found, "github_action", rel, name, ref)
        python_version = re.search(r"^\s*python-version:\s*[\"']?([^\"'\s]+)", workflow, re.M)
        if python_version:
            _set(found, "github_python_runtime", rel, "python", python_version.group(1))

    compose = root / "bin" / "lib" / "compose.py"
    if compose.exists():
        for reference in re.findall(r'["\']image["\']\s*:\s*["\']([^"\']+)', compose.read_text(encoding="utf-8")):
            if not reference.startswith(("localhost/", "${")):
                _set(found, "compose_image", relpath(root, compose), image_name(reference), reference)
    return found


EXTRACTED_KINDS = {
    "requirement", "pip_install", "npm", "container_from", "image_arg", "python_image_default",
    "compose_image", "apt_group", "node_setup", "git_ref", "github_action", "github_python_runtime",
}


def declaration_key(declaration: dict) -> str:
    return key_for(declaration["kind"], declaration["path"], declaration.get("package")
                   or declaration.get("name", ""))


def _source_matches(component: dict, declaration: dict) -> bool:
    source = component.get("source", {})
    kind = declaration.get("kind")
    if kind == "requirement" and source.get("type") == "pypi":
        return norm_package(source.get("package", "")) == norm_package(declaration.get("package", "")).split("[", 1)[0]
    if kind == "pip_install" and source.get("type") == "pypi":
        return norm_package(source.get("package", "")) == norm_package(declaration.get("package", ""))
    if kind == "npm" and source.get("type") == "npm":
        return source.get("package") == declaration.get("package")
    return True


def validate_inventory(root: Path, inventory: dict) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    actual = discover_inputs(root)
    ids: set[str] = set()
    declared: dict[str, str] = {}
    allowed_compat = {"unknown", "supported", "unsupported"}
    for component in inventory.get("components", []):
        cid = component.get("id", "<missing-id>")
        if cid in ids:
            errors.append(f"duplicate component id: {cid}")
        ids.add(cid)
        review = component.get("review") or {}
        if not review.get("owner") and not inventory.get("review_owner"):
            errors.append(f"{cid}: missing review owner")
        for field in ("last_reviewed", "outcome", "next_review", "evidence"):
            if field not in review:
                errors.append(f"{cid}: missing review field {field}")
        for field in ("last_reviewed", "next_review"):
            value = review.get(field)
            if value is not None:
                try:
                    if isinstance(value, dt.datetime):
                        value.date()
                    elif isinstance(value, dt.date):
                        pass
                    else:
                        dt.date.fromisoformat(str(value))
                except ValueError:
                    errors.append(f"{cid}: invalid review date {field}={value!r}")
        if not review.get("outcome"):
            errors.append(f"{cid}: missing review outcome")
        status = component.get("compatibility", {}).get("status")
        if status not in allowed_compat:
            errors.append(f"{cid}: invalid compatibility status {status!r}")
        if "installed_version" in component:
            errors.append(f"{cid}: installed_version must only be recorded after image inspection")
        declarations = component.get("declarations", [])
        for declaration in declarations:
            kind = declaration.get("kind")
            path = declaration.get("path", "")
            if path and not (root / path).is_file():
                errors.append(f"{cid}: declaration path does not exist: {path}")
            if kind == "manual":
                if path and (root / path).is_file() and declaration.get("term", "") not in (root / path).read_text(encoding="utf-8"):
                    errors.append(f"{cid}: manual declaration text not found in {path}: {declaration.get('term')}")
                continue
            if kind == "derived":
                parents = declaration.get("parents", [])
                if not parents:
                    errors.append(f"{cid}: derived declaration has no parent")
                for parent in parents:
                    if parent not in {c.get("id") for c in inventory.get("components", [])}:
                        errors.append(f"{cid}: broken derived link to {parent}")
                continue
            if kind not in EXTRACTED_KINDS:
                errors.append(f"{cid}: unsupported declaration kind {kind!r}")
                continue
            key = declaration_key(declaration)
            if key in declared:
                errors.append(f"duplicate inventory declaration: {key} ({declared[key]}, {cid})")
            declared[key] = cid
            if not _source_matches(component, declaration):
                errors.append(f"{cid}: upstream source does not match declaration package")

    for key in sorted(set(actual) - set(declared)):
        errors.append(f"missing dependency input from inventory: {key} = {actual[key]}")
    for key in sorted(set(declared) - set(actual)):
        errors.append(f"stale inventory declaration: {key} ({declared[key]})")
    return errors, actual


def _load_and_validate(root: Path, inventory_path: Path) -> tuple[dict, dict[str, object], list[str]]:
    inventory = load_inventory(inventory_path)
    errors, actual = validate_inventory(root, inventory)
    return inventory, actual, errors


def command_validate(root: Path, inventory_path: Path) -> int:
    try:
        inventory, actual, errors = _load_and_validate(root, inventory_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Dependency inventory: {len(inventory['components'])} components; {len(actual)} discovered inputs")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Inventory declarations and derived links: PASS")
    return 0


class LookupFailure(RuntimeError):
    pass


class RegistryAuthRequired(LookupFailure):
    def __init__(self, challenge: str):
        self.challenge = challenge
        super().__init__("registry requires anonymous bearer-token negotiation")


def fetch_json(url: str, headers: dict[str, str] | None = None,
               timeout: int = TIMEOUT_SECS) -> object:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RegistryAuthRequired(exc.headers.get("WWW-Authenticate", "")) from exc
        raise LookupFailure(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None)
        raise LookupFailure(f"{type(exc).__name__}: {reason or exc}") from exc


def is_prerelease(version: str) -> bool:
    return bool(re.search(r"(?:a|b|rc|alpha|beta|dev|pre|preview)(?:[.-]?\d|$)", version, re.I))


def version_key(version: str) -> tuple:
    normalized = version[1:] if version[:1].lower() == "v" else version
    return tuple((1, int(part)) if part.isdigit() else (0, part.lower())
                 for part in re.findall(r"\d+|[A-Za-z]+", normalized))


def newest(versions: list[str]) -> str | None:
    return max(versions, key=version_key) if versions else None


def _candidate_result(stable: str | None, prerelease: str | None = None,
                      detail: str | None = None) -> dict:
    if stable is None and prerelease is None:
        raise LookupFailure("source returned no matching version candidates")
    return {"status": "ok", "candidate": stable, "prerelease": prerelease, "detail": detail}


def _pypi_candidates(package: str, include_prerelease: bool, fetch) -> dict:
    url = f"https://pypi.org/pypi/{urllib.parse.quote(package, safe='')}/json"
    data = fetch(url)
    releases = data.get("releases", {})
    versions = [version for version, files in releases.items()
                if files and not any(file.get("yanked", False) for file in files)]
    stable = newest([v for v in versions if not is_prerelease(v)])
    pre = newest([v for v in versions if is_prerelease(v)]) if include_prerelease else None
    if stable is None:
        info_version = data.get("info", {}).get("version")
        if info_version and not is_prerelease(info_version):
            stable = info_version
    return _candidate_result(stable, pre)


def _npm_candidates(package: str, include_prerelease: bool, fetch) -> dict:
    url = "https://registry.npmjs.org/" + urllib.parse.quote(package, safe="@")
    data = fetch(url)
    tags = data.get("dist-tags", {})
    stable = tags.get("latest")
    pre = tags.get("next") if include_prerelease else None
    if stable and is_prerelease(stable):
        stable = None
    if pre and not is_prerelease(pre):
        pre = None
    return _candidate_result(stable, pre)


def _image_candidates(source: dict, include_prerelease: bool, fetch) -> dict:
    repository = source["repository"]
    url = f"https://hub.docker.com/v2/repositories/{repository}/tags?page_size=100"
    payload = fetch(url)
    tag_pattern = re.compile(source.get("tag_regex", ".*"))
    versions = [item.get("name", "") for item in payload.get("results", [])
                if tag_pattern.fullmatch(item.get("name", ""))]
    stable = newest([v for v in versions if not is_prerelease(v)])
    pre = newest([v for v in versions if is_prerelease(v)]) if include_prerelease else None
    return _candidate_result(stable, pre, "Docker Hub tag; digest not resolved")


def _ghcr_candidates(source: dict, include_prerelease: bool, fetch) -> dict:
    repository = source["repository"]
    url = f"https://ghcr.io/v2/{repository}/tags/list?n=100"
    try:
        payload = fetch(url)
    except RegistryAuthRequired as exc:
        fields = dict(re.findall(r'(\w+)="([^"]+)"', exc.challenge))
        realm = fields.get("realm", "")
        if not realm.startswith("https://"):
            raise LookupFailure("GHCR anonymous token challenge was unavailable") from exc
        query = {key: fields[key] for key in ("service", "scope") if fields.get(key)}
        token_url = realm + ("&" if "?" in realm else "?") + urllib.parse.urlencode(query)
        token_payload = fetch(token_url)
        token = token_payload.get("token") or token_payload.get("access_token")
        if not token:
            raise LookupFailure("GHCR token response contained no token")
        payload = fetch(url, {"Authorization": f"Bearer {token}"})
    tag_pattern = re.compile(source.get("tag_regex", ".*"))
    versions = [tag for tag in payload.get("tags", []) if tag_pattern.fullmatch(tag)]
    stable = newest([v for v in versions if not is_prerelease(v)])
    pre = newest([v for v in versions if is_prerelease(v)]) if include_prerelease else None
    return _candidate_result(stable, pre, "GHCR tag; digest not resolved")


def _github_release_candidates(repository: str, include_prerelease: bool, fetch) -> dict:
    url = f"https://api.github.com/repos/{repository}/releases?per_page=20"
    releases = fetch(url, {"Accept": "application/vnd.github+json"})
    stable = [item.get("tag_name", "") for item in releases
              if not item.get("draft") and not item.get("prerelease") and item.get("tag_name")]
    prerelease = [item.get("tag_name", "") for item in releases
                  if not item.get("draft") and item.get("prerelease") and item.get("tag_name")]
    return _candidate_result(newest(stable), newest(prerelease) if include_prerelease else None)


def _node_candidates(major: int, include_prerelease: bool, fetch) -> dict:
    releases = fetch("https://nodejs.org/dist/index.json")
    matching = [item.get("version", "").removeprefix("v") for item in releases
                if item.get("version", "").startswith(f"v{major}.")]
    stable = newest([v for v in matching if not is_prerelease(v)])
    prerelease = newest([v for v in matching if is_prerelease(v)]) if include_prerelease else None
    return _candidate_result(stable, prerelease, f"Node.js {major} stream")


def _github_ref_candidate(repository: str, ref: str, fetch) -> dict:
    encoded = urllib.parse.quote(ref, safe="")
    data = fetch(f"https://api.github.com/repos/{repository}/commits/{encoded}",
                 {"Accept": "application/vnd.github+json"})
    sha = data.get("sha")
    if not sha:
        raise LookupFailure("commit response did not contain a SHA")
    date = data.get("commit", {}).get("committer", {}).get("date", "date unknown")
    return {"status": "ok", "candidate": sha[:12], "prerelease": None,
            "detail": f"{ref} commit ({date})"}


def lookup_source(source: dict, include_prerelease: bool = False, ref: str | None = None,
                  fetch=fetch_json) -> dict:
    kind = source.get("type")
    if kind == "pypi":
        return _pypi_candidates(source["package"], include_prerelease, fetch)
    if kind == "npm":
        return _npm_candidates(source["package"], include_prerelease, fetch)
    if kind == "dockerhub_image":
        return _image_candidates(source, include_prerelease, fetch)
    if kind == "ghcr_image":
        return _ghcr_candidates(source, include_prerelease, fetch)
    if kind == "github_release":
        return _github_release_candidates(source["repository"], include_prerelease, fetch)
    if kind == "nodejs_release":
        return _node_candidates(int(source["major"]), include_prerelease, fetch)
    if kind == "github_ref":
        if not ref:
            raise LookupFailure("branch or tag ref is missing from its declaration")
        return _github_ref_candidate(source["repository"], ref, fetch)
    if kind == "derived":
        return {"status": "derived", "candidate": None, "prerelease": None,
                "detail": f"follows {source.get('parent', 'parent component')}"}
    if kind == "manual":
        return {"status": "manual", "candidate": None, "prerelease": None,
                "detail": "no package-version lookup; inspect the installed image or host"}
    raise LookupFailure(f"unsupported upstream source type {kind!r}")


def _component_ref(component: dict, actual: dict[str, object]) -> str | None:
    for declaration in component.get("declarations", []):
        if declaration.get("kind") == "git_ref":
            value = actual.get(declaration_key(declaration), {})
            if isinstance(value, dict):
                return value.get("ref")
    return None


def source_fixture_key(source: dict, ref: str | None = None) -> str:
    kind = source.get("type", "unknown")
    if kind in {"pypi", "npm"}:
        target = source.get("package", "")
    elif kind in {"dockerhub_image", "ghcr_image", "github_release", "github_ref"}:
        target = source.get("repository", "")
    elif kind == "nodejs_release":
        target = str(source.get("major", ""))
    else:
        target = ""
    if kind == "github_ref" and ref:
        target += "@" + ref
    return f"{kind}:{target}"


def perform_check(inventory: dict, actual: dict[str, object],
                  include_prerelease: bool = False, lookup=lookup_source) -> list[dict]:
    components = inventory["components"]
    query_cache: dict[str, dict] = {}
    query_specs: dict[str, tuple[dict, str | None]] = {}
    for component in components:
        source = component.get("source", {})
        if source.get("type") in {"manual", "derived"}:
            continue
        ref = _component_ref(component, actual) if source.get("type") == "github_ref" else None
        signature = json.dumps([source, ref, include_prerelease], sort_keys=True)
        query_specs[signature] = (source, ref)

    signatures = list(query_specs)
    if len(signatures) > MAX_LOOKUPS:
        for signature in signatures[MAX_LOOKUPS:]:
            query_cache[signature] = {"status": "failed", "error": f"lookup safety limit ({MAX_LOOKUPS}) exceeded"}
        signatures = signatures[:MAX_LOOKUPS]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for signature in signatures:
            source, ref = query_specs[signature]
            futures[executor.submit(lookup, source, include_prerelease=include_prerelease, ref=ref)] = signature
        for future, signature in ((future, futures[future]) for future in futures):
            try:
                query_cache[signature] = future.result()
            except Exception as exc:  # One upstream failure must not hide other results.
                query_cache[signature] = {"status": "failed", "error": str(exc)}

    today = dt.datetime.now(dt.timezone.utc).date()
    results = []
    by_id = {component["id"]: component for component in components}
    query_by_id = {}
    for component in components:
        source = component.get("source", {})
        if source.get("type") in {"manual", "derived"}:
            continue
        ref = _component_ref(component, actual) if source.get("type") == "github_ref" else None
        signature = json.dumps([source, ref, include_prerelease], sort_keys=True)
        query_by_id[component["id"]] = query_cache.get(signature)
    for component in components:
        source = component.get("source", {})
        kind = source.get("type")
        ref = _component_ref(component, actual) if kind == "github_ref" else None
        signature = json.dumps([source, ref, include_prerelease], sort_keys=True)
        result = query_cache.get(signature)
        if kind == "derived":
            parent = source.get("parent")
            parent_result = query_by_id.get(parent, {}) or {}
            parent_candidate = parent_result.get("candidate")
            parent_component = by_id.get(parent, {})
            if parent_component.get("source", {}).get("type") == "derived":
                parent_candidate = parent_result.get("parent_candidate")
            detail = f"follows {parent}; installed resolution unknown"
            if parent_candidate:
                detail += f" (parent candidate {parent_candidate})"
            result = {"status": "derived", "candidate": None, "parent_candidate": parent_candidate,
                      "prerelease": None, "detail": detail}
        if kind == "manual":
            result = lookup(source, include_prerelease=include_prerelease)
        review = component.get("review", {})
        reviewed = review.get("last_reviewed")
        if reviewed is None:
            review_age = "unreviewed"
        else:
            if isinstance(reviewed, dt.datetime):
                reviewed = reviewed.date()
            elif isinstance(reviewed, str):
                reviewed = dt.date.fromisoformat(reviewed)
            review_age = f"{(today - reviewed).days}d"
            if (today - reviewed).days > int(inventory.get("review_cadence_days", 30)):
                review_age += " overdue"
        declared = []
        for declaration in component.get("declarations", []):
            key = declaration_key(declaration) if declaration.get("kind") in EXTRACTED_KINDS else None
            if key and key in actual:
                value = actual[key]
                text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
                label = classify_declaration(declaration["kind"], value)
                declared.append(f"{text} [{label}; installed unknown]")
        results.append({
            "id": component.get("id", "?"), "name": component.get("name", ""),
            "declared": "; ".join(declared) or ("manual; installed unknown" if kind == "manual"
                                                       else "inherited/derived; installed unknown"),
            "result": result or {"status": "failed", "error": "no lookup result"},
            "compatibility": component.get("compatibility", {}).get("status", "unknown"),
            "review_age": review_age,
        })
    return results


def command_check(root: Path, inventory_path: Path, include_prerelease: bool,
                  fixture_responses_path: Path | None = None) -> int:
    try:
        inventory, actual, errors = _load_and_validate(root, inventory_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Dependency review ({dt.datetime.now(dt.timezone.utc).date().isoformat()})")
    print(f"Inventory validation: {'FAIL' if errors else 'PASS'} ({len(inventory['components'])} components)")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if include_prerelease:
        print("Candidate policy: stable plus prerelease candidates")
    else:
        print("Candidate policy: stable only (use --include-prerelease to include prereleases)")
    print("Available versions are candidates only; compatibility is recorded evidence, not inferred.")
    lookup = lookup_source
    if fixture_responses_path:
        try:
            fixture_responses = json.loads(fixture_responses_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot read fixture responses: {exc}", file=sys.stderr)
            return 2

        def fixture_lookup(source, include_prerelease=False, ref=None):
            if source.get("type") in {"manual", "derived"}:
                return lookup_source(source, include_prerelease=include_prerelease, ref=ref)
            key = source_fixture_key(source, ref)
            return fixture_responses.get(key, {"status": "failed", "error": "fixture has no response for " + key})

        lookup = fixture_lookup
    results = perform_check(inventory, actual, include_prerelease, lookup=lookup)
    print("ID | DECLARED | UPSTREAM | COMPATIBILITY | REVIEW | RESULT")
    failed = False
    for item in results:
        result = item["result"]
        status = result.get("status")
        if status == "failed":
            upstream = "unknown"
            detail = "LOOKUP FAILED: " + result.get("error", "unknown error")
            failed = True
        elif result.get("candidate"):
            upstream = result["candidate"]
            if result.get("prerelease"):
                upstream += " (pre " + result["prerelease"] + ")"
            detail = result.get("detail") or "candidate available"
        else:
            upstream = "unknown"
            detail = result.get("detail", status or "unknown")
        print(f"{item['id']} | {item['declared']} | {upstream} | {item['compatibility']} | {item['review_age']} | {detail}")
    print("Result: INCOMPLETE (one or more upstream lookups failed)" if failed else "Result: complete; review compatibility and evidence before upgrades")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "check"))
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: script checkout)")
    parser.add_argument("--inventory", type=Path, default=None, help="inventory YAML path")
    parser.add_argument("--include-prerelease", action="store_true", help="include prerelease upstream candidates")
    parser.add_argument("--fixture-responses", type=Path, default=None,
                        help="replay a JSON response fixture instead of making upstream requests")
    args = parser.parse_args(argv)
    inventory_path = args.inventory or (args.root / "config" / "dependencies.yaml")
    if args.command == "validate":
        return command_validate(args.root.resolve(), inventory_path.resolve())
    return command_check(args.root.resolve(), inventory_path.resolve(), args.include_prerelease,
                         args.fixture_responses.resolve() if args.fixture_responses else None)


if __name__ == "__main__":
    raise SystemExit(main())

"""Unit tests for bin/lib/portal_host.py.

Note: tests/unit/test_portal_host.py already covers bin/lib/portal_host.sh
(the shell implementation). This file covers bin/lib/portal_host.py (the
Python port).

Coverage required by task 3.3:
(a) empty host is loopback
(b) 127.0.0.1 is loopback
(c) 0.0.0.0 is wildcard but not loopback
(d) example.com is neither
(e) probe_base returns bracketed IPv6 literals
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from bin.lib.portal_host import (
    addr,
    check_exposure,
    is_loopback,
    is_wildcard,
    legacy_bind_notice,
    probe_base,
    public_base,
    resolve_api_key,
)


# ---------------------------------------------------------------------------
# is_loopback
# ---------------------------------------------------------------------------

class TestIsLoopback:
    def test_empty_host_is_loopback(self) -> None:
        assert is_loopback("") is True

    def test_localhost_is_loopback(self) -> None:
        assert is_loopback("localhost") is True

    def test_127_0_0_1_is_loopback(self) -> None:
        assert is_loopback("127.0.0.1") is True

    def test_127_network_is_loopback(self) -> None:
        assert is_loopback("127.0.0.2") is True

    def test_ipv6_loopback_is_loopback(self) -> None:
        assert is_loopback("::1") is True

    def test_public_ip_is_not_loopback(self) -> None:
        assert is_loopback("192.168.1.10") is False

    def test_example_com_is_not_loopback(self) -> None:
        assert is_loopback("example.com") is False


# ---------------------------------------------------------------------------
# is_wildcard
# ---------------------------------------------------------------------------

class TestIsWildcard:
    def test_0_0_0_0_is_wildcard(self) -> None:
        assert is_wildcard("0.0.0.0") is True

    def test_double_colon_is_wildcard(self) -> None:
        assert is_wildcard("::") is True

    def test_bracketed_double_colon_is_wildcard(self) -> None:
        assert is_wildcard("[::]") is True

    def test_0_0_0_0_not_loopback(self) -> None:
        # (c) 0.0.0.0 is wildcard but not loopback
        assert is_wildcard("0.0.0.0") is True
        assert is_loopback("0.0.0.0") is False

    def test_example_com_not_wildcard(self) -> None:
        # (d) example.com is neither
        assert is_wildcard("example.com") is False

    def test_example_com_not_loopback(self) -> None:
        assert is_loopback("example.com") is False

    def test_127_0_0_1_not_wildcard(self) -> None:
        assert is_wildcard("127.0.0.1") is False


# ---------------------------------------------------------------------------
# addr
# ---------------------------------------------------------------------------

class TestAddr:
    def test_plain_ipv4(self) -> None:
        assert addr("192.168.1.10") == "192.168.1.10"

    def test_ipv6_literal_bracketed(self) -> None:
        # (e) probe_base returns bracketed IPv6 literals
        assert addr("2001:db8::1") == "[2001:db8::1]"

    def test_already_bracketed_untouched(self) -> None:
        assert addr("[2001:db8::1]") == "[2001:db8::1]"

    def test_empty_gives_loopback(self) -> None:
        assert addr("") == "127.0.0.1"

    def test_hostname_unchanged(self) -> None:
        assert addr("example.com") == "example.com"


# ---------------------------------------------------------------------------
# public_base
# ---------------------------------------------------------------------------

class TestPublicBase:
    def test_empty_host_gives_localhost(self) -> None:
        assert public_base("", "64057") == "http://localhost:64057"

    def test_127_gives_localhost(self) -> None:
        assert public_base("127.0.0.1", "64057") == "http://localhost:64057"

    def test_wildcard_gives_localhost(self) -> None:
        assert public_base("0.0.0.0", "64057") == "http://localhost:64057"

    def test_public_ip_uses_host(self) -> None:
        assert public_base("192.168.1.10", "64057") == "http://192.168.1.10:64057"

    def test_ipv6_bracketed_in_url(self) -> None:
        assert public_base("2001:db8::1", "64057") == "http://[2001:db8::1]:64057"


# ---------------------------------------------------------------------------
# probe_base
# ---------------------------------------------------------------------------

class TestProbeBase:
    def test_localhost_probe(self) -> None:
        assert probe_base("127.0.0.1", "64057", "http") == "http://127.0.0.1:64057"

    def test_wildcard_probe_uses_127(self) -> None:
        assert probe_base("0.0.0.0", "64057", "http") == "http://127.0.0.1:64057"

    def test_empty_host_probe_uses_127(self) -> None:
        assert probe_base("", "64057", "http") == "http://127.0.0.1:64057"

    def test_public_ip_probe_uses_host(self) -> None:
        assert probe_base("192.168.1.10", "64057", "http") == "http://192.168.1.10:64057"

    def test_ipv6_literal_bracketed(self) -> None:
        # (e) probe_base returns bracketed IPv6 literals
        assert probe_base("::1", "64057", "https") == "https://[::1]:64057"


# ---------------------------------------------------------------------------
# check_exposure
# ---------------------------------------------------------------------------

class TestCheckExposure:
    def test_loopback_passes_silently(self) -> None:
        check_exposure("127.0.0.1", "64057")  # must not raise or exit

    def test_empty_host_passes_silently(self) -> None:
        check_exposure("", "64057")

    def test_non_loopback_with_key_passes(self) -> None:
        check_exposure("0.0.0.0", "64057", ga_api_key="mykey")

    def test_opt_out_passes_with_warning(self, capsys) -> None:
        check_exposure("0.0.0.0", "64057", ga_api_key_disabled="true")
        captured = capsys.readouterr()
        assert "explicitly disabled" in captured.err

    def test_non_loopback_no_key_exits(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            check_exposure("0.0.0.0", "64057")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# resolve_api_key
# ---------------------------------------------------------------------------

class TestResolveApiKey:
    def test_yaml_key_wins_over_stale_saved_key(self, tmp_path: Path) -> None:
        flag_file = tmp_path / "ga-api-key.flag"
        flag_file.write_text("old-key", encoding="utf-8")
        result = resolve_api_key(
            str(tmp_path),
            ga_api_key="new-key",
            ga_api_key_source="yaml",
        )
        assert result["ga_api_key"] == "new-key"
        assert (tmp_path / "ga-api-key").read_text(encoding="utf-8") == "new-key"

    def test_flag_wins_over_yaml(self, tmp_path: Path) -> None:
        result = resolve_api_key(
            str(tmp_path),
            api_key_flag_passed=True,
            flag_api_key="flag-key",
            ga_api_key="yaml-key",
            ga_api_key_source="yaml",
        )
        assert result["ga_api_key"] == "flag-key"

    def test_saved_key_used_when_nothing_else_set(self, tmp_path: Path) -> None:
        flag_file = tmp_path / "ga-api-key.flag"
        flag_file.write_text("old-key", encoding="utf-8")
        flag_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        result = resolve_api_key(str(tmp_path))
        assert result["ga_api_key"] == "old-key"

    def test_empty_flag_clears_and_falls_through_to_yaml(self, tmp_path: Path) -> None:
        flag_file = tmp_path / "ga-api-key.flag"
        flag_file.write_text("old-key", encoding="utf-8")
        result = resolve_api_key(
            str(tmp_path),
            api_key_flag_passed=True,
            flag_api_key="",
            ga_api_key="yaml-key",
            ga_api_key_source="yaml",
        )
        assert result["ga_api_key"] == "yaml-key"

    def test_deprecated_off_when_no_key(self, tmp_path: Path) -> None:
        result = resolve_api_key(str(tmp_path), ga_api_key_deprecated_off="true")
        assert result["ga_api_key_disabled"] == "true"
        assert (tmp_path / "ga-api-key").exists() is False

    def test_deprecated_off_never_disables_saved_key(self, tmp_path: Path) -> None:
        flag_file = tmp_path / "ga-api-key.flag"
        flag_file.write_text("saved-key", encoding="utf-8")
        result = resolve_api_key(str(tmp_path), ga_api_key_deprecated_off="true")
        assert result["ga_api_key"] == "saved-key"
        assert result["ga_api_key_disabled"] == ""

    def test_legacy_key_file_migrated_once(self, tmp_path: Path) -> None:
        eff = tmp_path / "ga-api-key"
        eff.write_text("legacy-key", encoding="utf-8")
        result = resolve_api_key(str(tmp_path))
        assert result["ga_api_key"] == "legacy-key"
        assert (tmp_path / "ga-api-key.flag").read_text(encoding="utf-8") == "legacy-key"


# ---------------------------------------------------------------------------
# legacy_bind_notice
# ---------------------------------------------------------------------------

class TestLegacyBindNotice:
    def test_notice_when_previous_compose_published_on_all_interfaces(
        self, tmp_path: Path, capsys
    ) -> None:
        compose = tmp_path / "compose.yml"
        compose.write_text(
            '    ports:\n      - "0.0.0.0:64057:64057"\n', encoding="utf-8"
        )
        legacy_bind_notice(str(compose), "127.0.0.1", "64057")
        captured = capsys.readouterr()
        assert "network.host" in captured.err

    def test_no_notice_on_fresh_install(self, tmp_path: Path, capsys) -> None:
        legacy_bind_notice(str(tmp_path / "nonexistent.yml"), "127.0.0.1", "64057")
        assert capsys.readouterr().err == ""

    def test_no_notice_when_host_is_wildcard(self, tmp_path: Path, capsys) -> None:
        compose = tmp_path / "compose.yml"
        compose.write_text(
            '      - "0.0.0.0:64057:64057"\n', encoding="utf-8"
        )
        legacy_bind_notice(str(compose), "0.0.0.0", "64057")
        assert capsys.readouterr().err == ""

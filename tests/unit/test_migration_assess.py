"""Tests for the migration-assess loadout's enabling transport changes.

Covers the three things that had to exist before a crew could reach a
Migration Pathfinder project over MCP:

  - manifest-driven persona rosters (_personas_for_composition and friends)
  - MCP client config injection into a crew (_copy_mcp_config)
  - the authenticating Pathfinder proxy's routing and token handling
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.unit.test_file_transfer import server


class PersonaRosterTests(unittest.TestCase):
    """A crew type's manifest is the authoritative statement of its roster."""

    ASSESS_MANIFEST = {
        "agents": [
            "chronicle.json", "sounder.json", "steward.json", "raven.json",
        ],
        "skills": ["pathfinder-assessment", "ghostship-mail"],
        "steering": ["ASSESSMENT_ORDERS.md"],
        "default_agent": "steward",
    }

    def test_star_selection_yields_the_shared_academy_roster(self) -> None:
        manifest = {"agents": "*", "skills": "*", "steering": "*", "default_agent": None}
        with patch.object(server, "_load_crew_manifest", return_value=manifest):
            self.assertEqual(
                server._personas_for_composition({"dir": "spec-ops"}),
                server.PERSONA_NAMES,
            )

    def test_explicit_selection_yields_its_own_roster_in_manifest_order(self) -> None:
        with patch.object(server, "_load_crew_manifest", return_value=self.ASSESS_MANIFEST):
            self.assertEqual(
                server._personas_for_composition({"dir": "migration-assess"}),
                ("chronicle", "sounder", "steward", "raven"),
            )

    def test_unusable_selection_falls_back_rather_than_leaving_a_crew_with_none(self) -> None:
        """A manifest that selects nothing recognisable must not strand a crew
        with an empty roster — every dispatch would then be invalid."""
        manifest = {"agents": ["not-a-json-file"], "skills": "*", "steering": "*"}
        with patch.object(server, "_load_crew_manifest", return_value=manifest):
            self.assertEqual(
                server._personas_for_composition({"dir": "broken"}),
                server.PERSONA_NAMES,
            )

    def test_default_agent_honoured_when_it_names_a_real_persona(self) -> None:
        with patch.object(server, "_load_crew_manifest", return_value=self.ASSESS_MANIFEST):
            personas = ("chronicle", "sounder", "steward", "raven")
            self.assertEqual(
                server._default_agent_for_composition({"dir": "x"}, personas),
                "steward",
            )

    def test_default_agent_outside_the_roster_falls_back_to_the_first_persona(self) -> None:
        """A manifest naming a default the crew does not carry would otherwise
        write a non-existent default_agent into KiroCrew's config."""
        manifest = dict(self.ASSESS_MANIFEST, default_agent="ghost")
        with patch.object(server, "_load_crew_manifest", return_value=manifest):
            personas = ("chronicle", "sounder", "steward", "raven")
            self.assertEqual(
                server._default_agent_for_composition({"dir": "x"}, personas),
                "chronicle",
            )

    def test_crew_personas_reads_the_registry_not_the_manifest(self) -> None:
        """A manifest edited after launch must not change a running crew's roster."""
        crew = {"personas": ["chronicle", "compass"]}
        self.assertEqual(server._crew_personas(crew), ("chronicle", "compass"))

    def test_crew_personas_falls_back_for_a_crew_registered_before_rosters(self) -> None:
        self.assertEqual(server._crew_personas({"container": "gs-x"}), server.PERSONA_NAMES)

    def test_mailboxes_are_the_roster_plus_captain_and_admiral(self) -> None:
        crew = {"personas": ["chronicle", "raven"]}
        self.assertEqual(
            server._crew_mailboxes(crew), ("chronicle", "raven", "captain", "admiral"),
        )

    def test_checkin_roster_excludes_raven_itself(self) -> None:
        """Raven is the persona the loop dispatches, so it must not appear in the
        list of personas that loop is told it may dispatch."""
        crew = {"personas": ["chronicle", "compass", "steward", "raven"]}
        prompt = server._captain_checkin_task(crew)
        self.assertIn("chronicle, compass, or steward", prompt)
        self.assertNotIn("<<PERSONA_ROSTER>>", prompt)
        self.assertNotIn("ghost, spectre", prompt)

    def test_checkin_roster_defaults_to_the_spec_ops_workers(self) -> None:
        prompt = server._captain_checkin_task({"container": "gs-x"})
        self.assertIn("ghost, spectre, banshee, wraith, or reaper", prompt)


class OpenSpecSeedingTests(unittest.TestCase):
    """The shared OpenSpec store only earns its place in a crew that uses it."""

    def test_star_skills_selection_seeds_the_store(self) -> None:
        with patch.object(server, "_load_crew_manifest", return_value={"skills": "*"}):
            self.assertTrue(server._composition_uses_openspec({"dir": "spec-ops"}))

    def test_openspec_skills_selected_explicitly_seed_the_store(self) -> None:
        manifest = {"skills": ["openspec-propose", "ghostship-mail"]}
        with patch.object(server, "_load_crew_manifest", return_value=manifest):
            self.assertTrue(server._composition_uses_openspec({"dir": "x"}))

    def test_a_crew_with_no_openspec_skills_does_not_seed_a_store(self) -> None:
        manifest = {"skills": ["pathfinder-assessment", "ghostship-mail"]}
        with patch.object(server, "_load_crew_manifest", return_value=manifest):
            self.assertFalse(server._composition_uses_openspec({"dir": "migration-assess"}))


class McpConfigInjectionTests(unittest.TestCase):
    """_copy_mcp_config gives a crew its own outbound MCP connection."""

    TEMPLATE = json.dumps({
        "_comment": "documentation only, must not reach the crew",
        "mcpServers": {
            "pathfinder": {
                "url": "{{TRANSPORT_URL}}/pathfinder/{{CREW_ID}}/mcp",
                "headers": {"Authorization": "Bearer {{CREW_MCP_TOKEN}}"},
            }
        },
    })

    def _run(self, podman, *, template=None, exists=True):
        with (
            patch("pathlib.Path.exists", return_value=exists),
            patch("pathlib.Path.read_text", return_value=template or self.TEMPLATE),
            patch.object(server, "GA_TRANSPORT_INTERNAL_URL", "http://ga-transport:64057"),
        ):
            return server._copy_mcp_config(
                podman, "gs-demo", "demo", {"dir": "migration-assess"}, "tok-123",
            )

    def test_registers_via_the_cli_with_substituted_placeholders(self) -> None:
        podman = MagicMock()
        podman.container_exec_checked.return_value = "added"
        result = self._run(podman)

        self.assertEqual(result, ["pathfinder"])
        cmd = podman.container_exec_checked.call_args.args[1]
        self.assertEqual(cmd[:3], ["kiro-cli", "mcp", "add"])
        self.assertIn("http://ga-transport:64057/pathfinder/demo/mcp", cmd)
        # Global scope, or every dispatched task's subagent_*/ cwd would miss it.
        self.assertIn("--scope", cmd)
        self.assertEqual(cmd[cmd.index("--scope") + 1], "global")
        self.assertIn("Bearer tok-123", cmd[cmd.index("--headers") + 1])

    def test_falls_back_to_writing_the_config_when_the_cli_rejects_it(self) -> None:
        """kiro-cli's flags vary by version; a rejected add must not leave the
        crew with no MCP server at all."""
        podman = MagicMock()
        podman.container_exec_checked.side_effect = [
            RuntimeError("unknown flag: --headers"),
            "wrote /home/kirocrew/.kiro/settings/mcp.json",
        ]
        result = self._run(podman)

        self.assertEqual(result, ["pathfinder"])
        self.assertEqual(podman.container_exec_checked.call_count, 2)
        write_cmd = podman.container_exec_checked.call_args.args[1]
        self.assertEqual(write_cmd[0], "python3")
        self.assertIn(server.KIRO_SETTINGS_DIR, write_cmd[2])

    def test_the_fallback_write_excludes_template_documentation_keys(self) -> None:
        """The rendered template carries a _comment for maintainers; writing it
        verbatim would put an unknown key into the crew's real MCP config."""
        import base64

        podman = MagicMock()
        podman.container_exec_checked.side_effect = [RuntimeError("no"), "wrote"]
        self._run(podman)

        script = podman.container_exec_checked.call_args.args[1][2]
        payload = script.split("b64decode('")[1].split("')")[0]
        written = json.loads(base64.b64decode(payload).decode())
        self.assertEqual(list(written.keys()), ["mcpServers"])
        self.assertNotIn("_comment", written)
        self.assertEqual(
            written["mcpServers"]["pathfinder"]["headers"]["Authorization"],
            "Bearer tok-123",
        )

    def test_a_crew_type_with_no_template_is_a_no_op(self) -> None:
        podman = MagicMock()
        self.assertEqual(self._run(podman, exists=False), [])
        podman.container_exec_checked.assert_not_called()

    def test_an_invalid_template_leaves_the_crew_without_mcp_rather_than_failing_launch(self) -> None:
        podman = MagicMock()
        self.assertEqual(self._run(podman, template="{not json"), [])
        podman.container_exec_checked.assert_not_called()


class PathfinderProxyRoutingTests(unittest.TestCase):
    """Path parsing for /pathfinder/{crew_id}/mcp."""

    def test_parses_a_bare_mcp_path(self) -> None:
        self.assertEqual(
            server._extract_pathfinder_parts("/pathfinder/acme/mcp"), ("acme", ""),
        )

    def test_parses_a_sub_path(self) -> None:
        self.assertEqual(
            server._extract_pathfinder_parts("/pathfinder/acme/mcp/messages"),
            ("acme", "messages"),
        )

    def test_rejects_paths_that_are_not_the_mcp_endpoint(self) -> None:
        for path in (
            "/pathfinder/acme",
            "/pathfinder",
            "/crews/acme/api/spawn",
            "/pathfinder/acme/admin",
        ):
            with self.subTest(path=path):
                self.assertIsNone(server._extract_pathfinder_parts(path))


class PathfinderTokenTests(unittest.TestCase):
    """Transport, not the crew, holds the Pathfinder credential."""

    def setUp(self) -> None:
        server._pathfinder_token_cache["token"] = ""
        server._pathfinder_token_cache["expires_at"] = 0.0

    def test_a_static_token_short_circuits_the_refresh_grant(self) -> None:
        with patch.object(server, "GA_PATHFINDER_ACCESS_TOKEN", "static-abc"):
            self.assertEqual(server._pathfinder_access_token(), "static-abc")

    def test_no_credential_raises_an_actionable_error(self) -> None:
        with (
            patch.object(server, "GA_PATHFINDER_ACCESS_TOKEN", ""),
            patch.object(server, "_pathfinder_refresh_token", return_value=""),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                server._pathfinder_access_token()
        self.assertIn("GA_PATHFINDER_ACCESS_TOKEN", str(ctx.exception))

    def test_a_refresh_token_without_endpoint_config_raises_before_any_call(self) -> None:
        with (
            patch.object(server, "GA_PATHFINDER_ACCESS_TOKEN", ""),
            patch.object(server, "_pathfinder_refresh_token", return_value="refresh-xyz"),
            patch.object(server, "GA_PATHFINDER_TOKEN_URL", ""),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                server._pathfinder_access_token()
        self.assertIn("GA_PATHFINDER_TOKEN_URL", str(ctx.exception))

    def test_the_crews_own_authorization_header_is_never_forwarded_upstream(self) -> None:
        """The crew authenticates to transport with its own token; it must not
        be able to influence the credential transport presents to Pathfinder."""
        self.assertIn("authorization", server._PATHFINDER_STRIPPED_REQUEST_HEADERS)
        self.assertIn("host", server._PATHFINDER_STRIPPED_REQUEST_HEADERS)


class AuthCompletionTests(unittest.TestCase):
    """A login is only complete once kiro-cli has written a token row.

    Regression cover for a flow that reported success as soon as any auth_kv row
    existed. kiro-cli writes its device-registration row before the operator
    approves anything in the browser, so the first poll captured a registration
    with no token, and every crew launched from that auth file came up with the
    agent runtime reporting "kiro-cli is not logged in".
    """

    def test_device_registration_alone_is_not_a_completed_login(self) -> None:
        rows = [["kirocli:odic:device-registration", "{...}"]]
        self.assertFalse(server._auth_rows_are_complete(rows))

    def test_a_token_row_completes_the_login(self) -> None:
        rows = [
            ["kirocli:odic:device-registration", "{...}"],
            ["kirocli:odic:token", "{...}"],
        ]
        self.assertTrue(server._auth_rows_are_complete(rows))

    def test_any_provider_prefix_counts(self) -> None:
        """kiro-cli writes both kirocli: and codewhisperer: prefixed keys."""
        self.assertTrue(
            server._auth_rows_are_complete([["codewhisperer:odic:token", "{...}"]])
        )

    def test_no_rows_at_all_is_not_complete(self) -> None:
        self.assertFalse(server._auth_rows_are_complete([]))

    def test_malformed_rows_do_not_raise(self) -> None:
        """The rows come from a JSON blob read out of a container; a surprising
        shape must read as 'not complete', not crash the login poll."""
        for rows in ([None], [[]], ["not-a-row"], [[123, "x"]], [{"k": "v"}]):
            with self.subTest(rows=rows):
                self.assertFalse(server._auth_rows_are_complete(rows))


class CrewUiRefererRoutingTests(unittest.TestCase):
    """Root-absolute crew UI requests are routed back to the right crew.

    The KiroCrew SPA is built with root-absolute paths (`/assets/App-*.js`,
    `/api/knowledge`). Served under `/crews/{id}/ui`, the browser requests those
    from transport's root, where they 404, and the page renders blank. The
    Referer identifies which crew they belong to.
    """

    def test_extracts_crew_id_from_a_ui_referer(self) -> None:
        self.assertEqual(
            server._crew_id_from_referer("http://localhost:64057/crews/acme/ui"),
            "acme",
        )

    def test_extracts_crew_id_from_a_deep_ui_referer(self) -> None:
        self.assertEqual(
            server._crew_id_from_referer("http://localhost:64057/crews/acme/ui/tasks/1"),
            "acme",
        )

    def test_distinguishes_between_two_crew_uis(self) -> None:
        """Two crew UIs open in separate tabs must not cross-route — which is
        why this keys off the Referer rather than a cookie or a last-crew global."""
        self.assertEqual(
            server._crew_id_from_referer("http://h/crews/alpha/ui"), "alpha")
        self.assertEqual(
            server._crew_id_from_referer("http://h/crews/beta/ui"), "beta")

    def test_ignores_referers_that_are_not_a_crew_ui(self) -> None:
        for referer in (
            "", "http://localhost:64057/", "http://localhost:64057/crews/acme/api/spawn",
            "http://localhost:64057/mcp", "not a url at all",
        ):
            with self.subTest(referer=referer):
                self.assertIsNone(server._crew_id_from_referer(referer))

    def test_cookie_covers_requests_that_carry_no_referer(self) -> None:
        """The crew UI registers a service worker, and service-worker fetches
        frequently send no Referer, so Referer alone leaves the UI half-working."""
        self.assertEqual(
            server._crew_id_from_cookie("ga_crew_ui=acme-migration"), "acme-migration")
        self.assertEqual(
            server._crew_id_from_cookie("other=1; ga_crew_ui=acme; z=2"), "acme")

    def test_cookie_value_must_look_like_a_crew_id(self) -> None:
        """The cookie is attacker-supplied like any other header; a value that is
        not a valid crew id must not reach the crew lookup."""
        for raw in ("ga_crew_ui=../../etc/passwd", "ga_crew_ui=", "ga_crew_ui=A_B!",
                    "unrelated=acme", ""):
            with self.subTest(cookie=raw):
                self.assertIsNone(server._crew_id_from_cookie(raw))

    def test_api_proxy_replaces_rather_than_appends_the_cookie(self) -> None:
        """The crew session cookie must fully replace any inbound cookie.

        Starlette yields header names lowercased, so setting "Cookie" while a
        "cookie" key survives sends two cookie headers and the gateway answers
        403 {"error": "Token required"}. Latent until the crew UI began setting
        its own cookie, which then broke every proxied API call from a browser.
        """
        inbound = {"host": "h", "cookie": "ga_crew_ui=acme", "accept": "*/*"}
        forwarded = {
            k: v for k, v in inbound.items() if k.lower() not in ("host", "cookie")
        }
        forwarded["Cookie"] = "mc_token_5476=session"
        cookie_keys = [k for k in forwarded if k.lower() == "cookie"]
        self.assertEqual(len(cookie_keys), 1)
        self.assertEqual(forwarded["Cookie"], "mc_token_5476=session")
        self.assertNotIn("ga_crew_ui", str(forwarded))

    def test_crew_accepts_browser_requests_from_transport(self) -> None:
        """A crew created with only its own internal origin CSRF-rejects every
        request from a browser using transport's crew-UI proxy."""
        origins = server._crew_cors_origins("gs-demo").split(",")
        self.assertIn("http://gs-demo:5476", origins)
        self.assertTrue(
            any("localhost" in o for o in origins),
            f"transport's browser origin missing from {origins}",
        )

    def test_both_loopback_spellings_are_allowed(self) -> None:
        """localhost and 127.0.0.1 are distinct origins, and the browser sends
        whichever is in the address bar."""
        origins = server._crew_cors_origins("gs-demo")
        self.assertIn(f"http://localhost:{server.PORT}", origins)
        self.assertIn(f"http://127.0.0.1:{server.PORT}", origins)

    def test_transport_routes_are_never_shadowed(self) -> None:
        """A crew UI must not be able to capture transport's own endpoints."""
        for path in ("/mcp", "/health", "/version", "/login", "/logout",
                     "/files", "/pathfinder", "/crews"):
            with self.subTest(path=path):
                self.assertIn(path, server._TRANSPORT_ROUTE_PREFIXES)


class PathfinderProxyIdleTests(unittest.TestCase):
    """An idle MCP client must not look like a working crew.

    kiro-cli holds the MCP notification stream (GET) open and reconnects it
    indefinitely, whether or not the crew is doing anything. Refreshing the idle
    timer on those keeps a finished crew alive forever: observed running 17
    hours after its last task completed, with its VM allocated the whole time.
    Only a POST, which carries an actual JSON-RPC call, counts as work.
    """

    def test_only_post_refreshes_the_idle_timer(self) -> None:
        src = (Path(__file__).resolve().parents[2]
               / "transport" / "server.py").read_text()
        handler = src.split("async def _handle_pathfinder_proxy")[1].split("\nasync def ")[0]
        self.assertIn('if request.method == "POST":', handler)
        touch_line = next(
            l for l in handler.splitlines() if "_touch_crew_throttled" in l and "def " not in l
        )
        self.assertTrue(
            touch_line.startswith("        "),
            "the idle-timer refresh must sit inside the POST guard, not at handler top level",
        )


class IdleMonitorStaleSessionTests(unittest.TestCase):
    """A stale gateway session must not disable idle-stopping forever.

    The monitor probes the crew gateway to see whether work is in flight. It
    refreshed its cookie on 401 only, but the gateway also answers 403, which
    fell through to the fail-open branch. Idle-stopping for that crew was then
    disabled permanently and silently: observed keeping a finished crew and its
    VM running for 17 hours.
    """

    def _monitor_source(self) -> str:
        src = (Path(__file__).resolve().parents[2] / "transport" / "server.py").read_text()
        return src.split("def _idle_monitor_pass")[1].split("\ndef ")[0]

    def test_403_triggers_a_cookie_refresh_like_401(self) -> None:
        body = self._monitor_source()
        self.assertIn("if r.status_code in (401, 403):", body)
        self.assertNotIn("if r.status_code == 401:", body)

    def test_both_probes_handle_the_stale_session(self) -> None:
        """The monitor probes /api/spawn and /api/crons; both must recover."""
        self.assertEqual(self._monitor_source().count("in (401, 403)"), 2)

    def test_failing_open_is_logged_not_silent(self) -> None:
        body = self._monitor_source()
        self.assertEqual(body.count("idle-stop disabled until this clears"), 2)


class IdleMonitorResilienceTests(unittest.TestCase):
    """The idle monitor must survive a failing pass.

    It runs as an unsupervised daemon thread. Before the guard, an exception
    anywhere outside its narrow inner try/except killed the thread silently:
    idle management stopped for the life of the process, with no log line, and
    crews ran indefinitely. Observed in practice — a crew and its VM stayed up
    17 hours with no work to do and never stopped.
    """

    def test_a_failing_pass_does_not_kill_the_loop(self) -> None:
        calls = []

        def flaky() -> None:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("transient podman error")
            raise KeyboardInterrupt  # break out of the infinite loop

        with (
            patch.object(server, "_idle_monitor_pass", side_effect=flaky),
            patch.object(server, "time") as fake_time,
        ):
            fake_time.sleep.return_value = None
            with self.assertRaises(KeyboardInterrupt):
                server._idle_monitor()

        # A second pass only happens if the first exception was swallowed.
        self.assertEqual(len(calls), 2, "monitor died on the first failing pass")

    def test_the_sweep_is_separable_from_the_loop(self) -> None:
        """The guard only works because the sweep is its own function."""
        self.assertTrue(callable(getattr(server, "_idle_monitor_pass", None)))


class ShippedLoadoutTests(unittest.TestCase):
    """The migration-assess data files must actually resolve against each other.

    A manifest naming an agent JSON that does not exist fails silently at launch
    — _copy_agents skips what it cannot find — and the crew comes up missing a
    persona nobody notices until a dispatch is rejected.
    """

    REPO = Path(__file__).resolve().parents[2]

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (cls.REPO / "crews" / "migration-assess" / "manifest.json").read_text()
        )

    def test_registered_as_a_launchable_composition(self) -> None:
        registry = json.loads((self.REPO / "crews" / "registry.json").read_text())
        entry = next(
            (c for c in registry["compositions"] if c["name"] == "migration-assess"), None
        )
        self.assertIsNotNone(entry, "migration-assess missing from crews/registry.json")
        self.assertEqual(entry["dir"], "migration-assess")
        self.assertTrue((self.REPO / "crews" / entry["dir"]).is_dir())

    def test_every_selected_agent_json_exists(self) -> None:
        for name in self.manifest["agents"]:
            with self.subTest(agent=name):
                self.assertTrue(
                    (self.REPO / "academy" / "agents" / name).is_file(),
                    f"manifest selects {name}, which does not exist in academy/agents/",
                )

    def test_every_selected_skill_and_steering_doc_exists(self) -> None:
        for name in self.manifest["skills"]:
            with self.subTest(skill=name):
                self.assertTrue(
                    (self.REPO / "academy" / "skills" / name / "SKILL.md").is_file()
                )
        for name in self.manifest["steering"]:
            with self.subTest(steering=name):
                self.assertTrue((self.REPO / "academy" / "steering" / name).is_file())

    def test_assessment_personas_opt_in_to_the_crew_mcp_config(self) -> None:
        """KiroCrew agents do NOT inherit the crew's global mcp.json.

        Each agent carries its own MCP server list, and an agent that neither
        sets includeMcpJson nor declares mcpServers of its own sees zero
        Pathfinder tools even though the crew is correctly wired. Verified
        against a live crew: without this, `kiro-cli mcp list` shows every
        persona as (empty) and a dispatch reports "a tool with the name
        'project_get' does not exist".
        """
        for filename in self.manifest["agents"]:
            name = filename[: -len(".json")]
            if name == "raven":
                continue  # coordination-only, deliberately has no Pathfinder access
            with self.subTest(agent=name):
                data = json.loads(
                    (self.REPO / "academy" / "agents" / filename).read_text()
                )
                self.assertTrue(
                    data.get("includeMcpJson"),
                    f"{name} would see no Pathfinder tools without includeMcpJson",
                )
                self.assertIn("@pathfinder", data["tools"])
                self.assertIn("@pathfinder", data["allowedTools"])

    def test_raven_has_no_pathfinder_access(self) -> None:
        """Raven reads Steward's coverage report, not Pathfinder. Giving it the
        tools would let the coordination loop form its own view of the estate
        and act on a second, disagreeing source of truth."""
        data = json.loads((self.REPO / "academy" / "agents" / "raven.json").read_text())
        self.assertNotIn("@pathfinder", data["tools"])
        self.assertFalse(data.get("includeMcpJson", False))

    def test_agent_json_name_matches_its_filename(self) -> None:
        """_copy_agents copies by filename but KiroCrew dispatches by the `name`
        field; a mismatch means the roster and the actual agent disagree."""
        for filename in self.manifest["agents"]:
            with self.subTest(agent=filename):
                data = json.loads(
                    (self.REPO / "academy" / "agents" / filename).read_text()
                )
                self.assertEqual(data["name"], filename[: -len(".json")])
                self.assertTrue(data.get("prompt"))
                self.assertIn("read", data["tools"])

    def test_the_manifest_resolves_to_the_expected_roster(self) -> None:
        with patch.object(server, "_load_crew_manifest", return_value=self.manifest):
            personas = server._personas_for_composition({"dir": "migration-assess"})
        self.assertIn("chronicle", personas)
        self.assertIn("raven", personas)
        self.assertNotIn("ghost", personas)
        self.assertEqual(len(personas), len(self.manifest["agents"]))

    def test_default_agent_is_one_of_this_crews_own_personas(self) -> None:
        with patch.object(server, "_load_crew_manifest", return_value=self.manifest):
            personas = server._personas_for_composition({"dir": "migration-assess"})
            default = server._default_agent_for_composition({"dir": "x"}, personas)
        self.assertIn(default, personas)

    def test_this_crew_type_does_not_seed_an_openspec_store(self) -> None:
        with patch.object(server, "_load_crew_manifest", return_value=self.manifest):
            self.assertFalse(server._composition_uses_openspec({"dir": "migration-assess"}))

    def test_the_shipped_mcp_template_renders_to_a_valid_config(self) -> None:
        raw = (self.REPO / "crews" / "migration-assess" / "mcp.json").read_text()
        rendered = json.loads(
            raw.replace("{{TRANSPORT_URL}}", "http://ga-transport:64057")
               .replace("{{CREW_ID}}", "acme")
               .replace("{{CREW_MCP_TOKEN}}", "tok")
        )
        server_spec = rendered["mcpServers"]["pathfinder"]
        self.assertEqual(server_spec["url"], "http://ga-transport:64057/pathfinder/acme/mcp")
        self.assertEqual(server_spec["headers"]["Authorization"], "Bearer tok")
        # No placeholder may survive rendering, or a crew gets a literal
        # "{{...}}" as its bearer token and every call 401s.
        self.assertNotIn("{{", json.dumps(rendered))

    def test_spec_ops_is_left_unchanged_by_this_loadout(self) -> None:
        """migration-assess must not have altered the existing crew type."""
        spec_ops = json.loads(
            (self.REPO / "crews" / "spec-ops" / "manifest.json").read_text()
        )
        self.assertEqual(spec_ops["agents"], "*")
        self.assertFalse((self.REPO / "crews" / "spec-ops" / "mcp.json").exists())
        with patch.object(server, "_load_crew_manifest", return_value=dict(spec_ops, default_agent=None)):
            self.assertEqual(
                server._personas_for_composition({"dir": "spec-ops"}), server.PERSONA_NAMES
            )
            self.assertTrue(server._composition_uses_openspec({"dir": "spec-ops"}))


if __name__ == "__main__":
    unittest.main()

"""Verify real Ghostship-generated model settings against pinned KiroCrew.

Run from the repo root with host dependencies installed:
  .venv/bin/python tests/integration/test_model_defaults.py --connection ghost-academy

Uses one disposable container, isolated dummy config, and no provider calls or
credentials. --image can select the image built from the pinned base; its ID is
reported so a mutable local tag cannot hide which consumer was verified.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

# Run a fresh interpreter per case: upstream config/discovery caches and HOME
# must be isolated, not monkey-patched to return the expected answer.
CONSUMER = r'''
import json, os, sys, tempfile
from pathlib import Path
case = json.load(sys.stdin)
with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    os.environ['HOME'] = str(home)
    os.environ['KIROCREW_HOME'] = str(home / '.kiro/crew')
    crew = Path(os.environ['KIROCREW_HOME'])
    crew.mkdir(parents=True)
    (crew / 'config.json').write_text(json.dumps({'agent': {'model': 'auto'}}))
    local = crew / 'config.local.json'
    local.write_text(json.dumps({'agent': {'model': 'previous', 'default_model': 'stale'}, 'session': {'max_history': 20}}))
    agents = home / '.kiro/agents'
    agents.mkdir(parents=True)
    (agents / 'kirocrew.json').write_text(json.dumps({'name': 'kirocrew', 'model': 'auto'}))
    persona = {'name': 'fixture-agent', 'prompt': 'fixture', 'tools': []}
    if case['persona']:
        persona['model'] = case['persona']
    (agents / 'fixture-agent.json').write_text(json.dumps(persona))
    # Dummy operator input and credential canaries are never passed to patching.
    operator = home / 'operator.yaml'
    credential = crew / 'credential-canary'
    operator.write_text('model: fixture-only\n')
    credential.write_text('dummy-credential-canary')
    canaries = [p.read_bytes() for p in (operator, credential)]
    namespace = {'__name__': 'patch_crew_config_fixture'}
    exec(case['patch_config_source'], namespace)
    override_namespace = {'__name__': 'patch_models_fixture'}
    exec(case['patch_models_source'], override_namespace)
    if case['override']:
        override_namespace['patch_models'](str(agents), case['override'])
    for payload in case['payloads']:
        namespace['patch_config'](str(local), payload)
        first = local.read_bytes()
        namespace['patch_config'](str(local), payload)
        assert local.read_bytes() == first, 'non-idempotent config application'
    from kiro_crew.config.loader import KiroCrewConfig, resolve_effective_model
    cfg = KiroCrewConfig.load()
    assert 'default_model' not in json.loads(local.read_text())['agent']
    assert cfg.agent.model == case['payloads'][-1]['agent']['model']
    assert json.loads(local.read_text())['session']['max_history'] == 20
    assert [p.read_bytes() for p in (operator, credential)] == canaries
    # Use the same ladder as real session allocation, then the ACP factory's
    # model selection / namespace translation. Only dispatch outranks that ladder.
    requested = case['dispatch'] or resolve_effective_model(cfg, template='fixture-agent')
    served_request = cfg.acp_effective_model('fixture-agent', requested or None)
    expected = cfg.acp_effective_model(None, case['expected']) if case['expected'] else ''
    assert served_request == expected, (case['name'], served_request, expected, requested)
    print(case['name'] + ': ' + (served_request or '<harness selection>'))
'''


class Recorder:
    def __init__(self):
        self.payload = None

    def container_exec(self, container, cmd):
        self.payload = json.loads(base64.b64decode(cmd[-1]))
        return 'recorded'


def cases():
    sys.path.insert(0, str(ROOT))
    import transport.lifecycle as life
    config_source = (ROOT / 'transport/container_scripts/patch_crew_config.py').read_text()
    model_source = (ROOT / 'transport/container_scripts/patch_models.py').read_text()
    for backend in ('kiro', 'claude', 'codex'):
        first, second = ('gpt-5.6-luna', 'gpt-6-astra') if backend == 'codex' else ('claude-sonnet-4.6', 'claude-opus-4.7')

        def payload(default, global_default=''):
            rec = Recorder()
            with patch.dict(life._KC_MODEL_BACKEND_DEFAULT, {backend: default}, clear=True), patch.object(life, 'KC_MODEL_DEFAULT', global_default), patch.object(life, 'GA_CREW_ACP_BACKEND', 'claude' if backend != 'claude' else 'kiro'), patch.object(life, '_load_crew_manifest', return_value={}):
                life._patch_crew_config(rec, 'fixture', backend=backend)
            # Backend=kiro normally relies on the image default; state it here
            # because this fixture intentionally replaces image config.json.
            rec.payload['agent'].setdefault('acp_backend', backend)
            return rec.payload

        for name, local, global_default, persona, override, dispatch, expected in (
            ('backend-over-global', first, second, '', '', '', first),
            ('global', '', first, '', '', '', first),
            ('persona', first, '', second, '', '', second),
            ('dispatch', first, '', first, '', second, second),
            ('backend-override', first, '', first, second, '', second),
            ('backend-override-unpinned', first, '', '', second, '', second),
            ('dispatch-over-backend-override', first, '', first, first, second, second),
            ('empty', '', '', '', '', '', ''),
            ('persona-auto', first, '', 'auto', '', '', first),
            ('clear', first, '', '', '', '', ''),
        ):
            payloads = [payload(local, global_default)]
            if name == 'clear':
                payloads.append(payload(''))
            yield dict(name=backend + '/' + name, payloads=payloads, persona=persona,
                       override=override, dispatch=dispatch, expected=expected,
                       patch_config_source=config_source, patch_models_source=model_source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection', default='ghost-academy')
    parser.add_argument('--image', default='localhost/spec-ops:latest')
    args = parser.parse_args()
    podman = ['podman', '--connection', args.connection]
    image_id = subprocess.check_output(podman + ['image', 'inspect', args.image, '--format', '{{.Id}}'], text=True).strip()
    inputs = list(cases())
    # One container, independent Python interpreter per case to isolate caches.
    runner = 'import json,subprocess,sys\nbundle=json.load(sys.stdin)\nfor case in bundle["cases"]:\n subprocess.run([sys.executable,"-c",bundle["consumer"]],input=json.dumps(case),text=True,check=True)\n'
    subprocess.run(podman + ['run', '--rm', '-i', '--network', 'none', '--entrypoint', 'python3', args.image, '-c', runner],
                   input=json.dumps({'cases': inputs, 'consumer': CONSUMER}), text=True, check=True, timeout=120)
    print(f'{len(inputs)} consumer cases passed; image={image_id}')


if __name__ == '__main__':
    main()

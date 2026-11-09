"""Reapplication must clear stale model state without changing unrelated config."""
import json
import pytest
from transport.container_scripts.patch_crew_config import patch_config


@pytest.mark.parametrize('legacy', [True, False])
def test_model_fallback_change_and_clear(tmp_path, legacy):
    config = tmp_path / 'config.local.json'
    agent = {'model': 'previous', 'sandbox': 'auto'}
    if legacy:
        agent['default_model'] = 'ignored-legacy'
    config.write_text(json.dumps({'agent': agent, 'session': {'keep': True}}))
    for model in ('new-fallback', 'auto'):
        overrides = {'agent': {'model': model}}
        patch_config(str(config), overrides)
        expected = {'agent': {'model': model, 'sandbox': 'auto'}, 'session': {'keep': True}}
        assert json.loads(config.read_text()) == expected
        before = config.read_bytes()
        patch_config(str(config), overrides)
        assert config.read_bytes() == before


def test_unrelated_patch_does_not_migrate_model(tmp_path):
    config = tmp_path / 'config.local.json'
    config.write_text(json.dumps({'agent': {'default_model': 'legacy', 'model': 'manual'}}))
    patch_config(str(config), {'session': {'keep': True}})
    assert json.loads(config.read_text())['agent'] == {'default_model': 'legacy', 'model': 'manual'}


@pytest.mark.parametrize('initial_model', [None, 'auto', 'another-model'])
def test_backend_override_applies_to_unpinned_personas(tmp_path, initial_model):
    from transport.container_scripts.patch_models import patch_models
    persona = {'name': 'fixture'}
    if initial_model is not None:
        persona['model'] = initial_model
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps(persona))
    assert patch_models(str(tmp_path), 'operator-choice') == ['fixture.json']
    assert json.loads(path.read_text())['model'] == 'operator-choice'
    assert patch_models(str(tmp_path), 'operator-choice') == []

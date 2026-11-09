"""The temporary upstream patch must reject drift instead of skipping a seal."""
import runpy
from pathlib import Path
import pytest

patch_module = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'crews/spec-ops/patch_sandbox_seal.py'))


def test_rejects_missing_upstream_seal():
    with pytest.raises(RuntimeError, match='review TRN-312'):
        patch_module['patch']('upstream changed')


def test_rejects_duplicate_upstream_seal():
    with pytest.raises(RuntimeError, match='review TRN-312'):
        patch_module['patch'](patch_module['ORIGINAL'] * 2)

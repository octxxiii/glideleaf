from pathlib import Path

import pytest

from scripts.prepare_native_drivers import generate
from winuc import native_driver as native


def test_generation_creates_reviewable_sources_without_installing_or_signing(tmp_path):
    folders = generate(tmp_path)
    assert len(folders) == len(native.SUPPORTED_IDS)
    assert all((folder / "glideleaf.inf").is_file() for folder in folders)
    assert not list(tmp_path.rglob("*.cat"))
    assert not list(tmp_path.rglob("*.exe"))
    assert not native.readiness(root=tmp_path)["ready"]


def test_generation_never_overwrites_a_signed_catalog(tmp_path):
    folders = generate(tmp_path)
    catalog = folders[0] / "glideleaf.cat"
    catalog.write_bytes(b"existing signed artifact")
    with pytest.raises(RuntimeError, match="fresh output"):
        generate(tmp_path)
    assert catalog.read_bytes() == b"existing signed artifact"

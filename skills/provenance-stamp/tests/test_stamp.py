"""Tests for provenance-stamp/scripts/stamp.py.

Coverage:
- compute_sha256: known content, empty file, hex format
- write_meta: sidecar creation, required fields, sha256, all optional params,
              inputs, custom out path, extra kwargs, missing artifact
- read_meta: round-trip, missing sidecar
- verify: unchanged artifact, tampered artifact, output_sha256 compatibility
- CLI: stamp, verify, show subcommands
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from stamp import compute_sha256, read_meta, verify, write_meta, _meta_path_for


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _expected_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# compute_sha256
# ---------------------------------------------------------------------------


def test_sha256_known_content(tmp_path):
    content = b"hello, provenance\n"
    f = _make_file(tmp_path, "a.txt", content)
    assert compute_sha256(f) == _expected_sha256(content)


def test_sha256_empty_file(tmp_path):
    f = _make_file(tmp_path, "empty.txt", b"")
    assert compute_sha256(f) == _expected_sha256(b"")


def test_sha256_is_64_hex(tmp_path):
    f = _make_file(tmp_path, "b.txt", b"data")
    result = compute_sha256(f)
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_sha256_changes_with_content(tmp_path):
    f = _make_file(tmp_path, "c.txt", b"version1")
    h1 = compute_sha256(f)
    f.write_bytes(b"version2")
    h2 = compute_sha256(f)
    assert h1 != h2


# ---------------------------------------------------------------------------
# write_meta — basics
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"artifact", "sha256", "stamped_at", "fetched_at", "tool_version"}


def test_write_meta_creates_sidecar(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"col1\tcol2\n1\t2\n")
    meta = write_meta(f)
    sidecar = _meta_path_for(f)
    assert sidecar.exists()
    assert json.loads(sidecar.read_text()) == meta


def test_write_meta_required_fields(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"data")
    meta = write_meta(f)
    missing = REQUIRED_FIELDS - set(meta)
    assert not missing, f"missing fields: {missing}"


def test_write_meta_sha256_correct(tmp_path):
    content = b"result data\n"
    f = _make_file(tmp_path, "out.tsv", content)
    meta = write_meta(f)
    assert meta["sha256"] == _expected_sha256(content)


def test_write_meta_artifact_name(tmp_path):
    f = _make_file(tmp_path, "mygene.tsv", b"x")
    meta = write_meta(f)
    assert meta["artifact"] == "mygene.tsv"


def test_write_meta_sidecar_is_valid_json(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    write_meta(f)
    sidecar = _meta_path_for(f)
    data = json.loads(sidecar.read_text())
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# write_meta — provenance fields
# ---------------------------------------------------------------------------


def test_write_meta_source_url(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    meta = write_meta(f, source_url="https://example.com/data.gz")
    assert meta["source_url"] == "https://example.com/data.gz"


def test_write_meta_doi(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    meta = write_meta(f, doi="10.1093/nar/gkac1052")
    assert meta["doi"] == "10.1093/nar/gkac1052"


def test_write_meta_data_version(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    meta = write_meta(f, data_version="2026-05-01")
    assert meta["data_version"] == "2026-05-01"


def test_write_meta_fetched_at(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    meta = write_meta(f, fetched_at="2026-05-01T14:23:00Z")
    assert meta["fetched_at"] == "2026-05-01T14:23:00Z"


def test_write_meta_fetched_at_defaults_to_stamped_at(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    meta = write_meta(f)
    assert meta["fetched_at"] == meta["stamped_at"]


def test_write_meta_fetched_at_can_differ_from_stamped_at(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    meta = write_meta(f, fetched_at="2026-01-01T00:00:00Z")
    assert meta["fetched_at"] != meta["stamped_at"]


def test_write_meta_params_recorded(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    meta = write_meta(f, params={"species": "human", "aspect": "BP"})
    assert meta["params"] == {"species": "human", "aspect": "BP"}


def test_write_meta_inputs_recorded(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"result")
    inp = _make_file(tmp_path, "source.gz", b"raw input")
    meta = write_meta(f, inputs=[inp])
    assert str(inp) in meta["inputs"]
    assert meta["inputs"][str(inp)] == _expected_sha256(b"raw input")


def test_write_meta_multiple_inputs(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    a = _make_file(tmp_path, "a.gz", b"aaa")
    b = _make_file(tmp_path, "b.gz", b"bbb")
    meta = write_meta(f, inputs=[a, b])
    assert len(meta["inputs"]) == 2


def test_write_meta_custom_out_path(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    custom = tmp_path / "provenance" / "out.meta.json"
    custom.parent.mkdir()
    meta = write_meta(f, out=custom)
    assert custom.exists()
    assert json.loads(custom.read_text()) == meta
    assert not _meta_path_for(f).exists()


def test_write_meta_extra_kwargs(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    meta = write_meta(f, pipeline="rnaseq-v2", organism="Mus musculus")
    assert meta["pipeline"] == "rnaseq-v2"
    assert meta["organism"] == "Mus musculus"


def test_write_meta_missing_artifact_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        write_meta(tmp_path / "nonexistent.tsv")


# ---------------------------------------------------------------------------
# read_meta
# ---------------------------------------------------------------------------


def test_read_meta_round_trip(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"data")
    written = write_meta(
        f, source_url="https://x.com", doi="10.1234/fake", data_version="v1"
    )
    assert read_meta(f) == written


def test_read_meta_missing_sidecar_raises(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"data")
    with pytest.raises(FileNotFoundError):
        read_meta(f)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def test_verify_passes_unchanged(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"unchanged content\n")
    write_meta(f)
    assert verify(f) is True


def test_verify_fails_after_modification(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"original")
    write_meta(f)
    f.write_bytes(b"tampered")
    assert verify(f) is False


def test_verify_accepts_output_sha256_field(tmp_path):
    """verify() must accept 'output_sha256' used by sibling skill sidecars."""
    content = b"skill artifact\n"
    f = _make_file(tmp_path, "out.tsv", content)
    _meta_path_for(f).write_text(json.dumps({
        "output_sha256": _expected_sha256(content),
        "fetched_at": "2026-05-01T00:00:00Z",
    }))
    assert verify(f) is True


def test_verify_missing_sidecar_raises(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    with pytest.raises(FileNotFoundError):
        verify(f)


def test_verify_sidecar_without_sha256_raises(tmp_path):
    f = _make_file(tmp_path, "out.tsv", b"x")
    _meta_path_for(f).write_text(json.dumps({"fetched_at": "2026-05-01T00:00:00Z"}))
    with pytest.raises(KeyError):
        verify(f)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_stamp_creates_sidecar(tmp_path):
    from stamp import main
    f = _make_file(tmp_path, "artifact.tsv", b"hello")
    rc = main(["stamp", str(f)])
    assert rc == 0
    assert _meta_path_for(f).exists()


def test_cli_stamp_source_url(tmp_path):
    from stamp import main
    f = _make_file(tmp_path, "artifact.tsv", b"hello")
    rc = main(["stamp", str(f), "--source-url", "https://example.org/data.gz"])
    assert rc == 0
    meta = json.loads(_meta_path_for(f).read_text())
    assert meta["source_url"] == "https://example.org/data.gz"


def test_cli_stamp_doi(tmp_path):
    from stamp import main
    f = _make_file(tmp_path, "artifact.tsv", b"hello")
    rc = main(["stamp", str(f), "--doi", "10.1093/nar/gkac1052"])
    assert rc == 0
    meta = json.loads(_meta_path_for(f).read_text())
    assert meta["doi"] == "10.1093/nar/gkac1052"


def test_cli_stamp_data_version(tmp_path):
    from stamp import main
    f = _make_file(tmp_path, "artifact.tsv", b"hello")
    rc = main(["stamp", str(f), "--data-version", "2026-05-01"])
    assert rc == 0
    meta = json.loads(_meta_path_for(f).read_text())
    assert meta["data_version"] == "2026-05-01"


def test_cli_stamp_params(tmp_path):
    from stamp import main
    f = _make_file(tmp_path, "artifact.tsv", b"hello")
    rc = main(["stamp", str(f), "--param", "species", "human", "--param", "aspect", "BP"])
    assert rc == 0
    meta = json.loads(_meta_path_for(f).read_text())
    assert meta["params"] == {"species": "human", "aspect": "BP"}


def test_cli_verify_ok(tmp_path, capsys):
    from stamp import main
    f = _make_file(tmp_path, "artifact.tsv", b"hello")
    write_meta(f)
    rc = main(["verify", str(f)])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_cli_verify_fail(tmp_path):
    from stamp import main
    f = _make_file(tmp_path, "artifact.tsv", b"hello")
    write_meta(f)
    f.write_bytes(b"tampered")
    rc = main(["verify", str(f)])
    assert rc == 1


def test_cli_show_prints_json(tmp_path, capsys):
    from stamp import main
    f = _make_file(tmp_path, "artifact.tsv", b"x")
    write_meta(f, source_url="https://x.org", doi="10.1234/test")
    rc = main(["show", str(f)])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["source_url"] == "https://x.org"
    assert data["doi"] == "10.1234/test"

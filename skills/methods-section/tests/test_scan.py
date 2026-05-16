"""Tests for methods-section/scripts/scan.py.

Coverage:
- parse_requirements_txt: pinned versions, >=, comments/options stripped, language tag
- parse_renv_lock: packages, R version, source field, language tag
- parse_conda_yaml: deps, version, python_version extraction
- scan_directory: fixture-based end-to-end for py_project, r_project, snakemake_project
- Schema invariants: all required keys present, tool fields complete
- CLI: writes JSON, handles missing directory
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scan import (
    parse_conda_yaml,
    parse_requirements_txt,
    parse_renv_lock,
    scan_directory,
)

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_KEYS = {
    "scan_root", "scanned_at", "python_version", "r_version",
    "tools", "artifacts", "workflows", "lockfiles_found",
}
TOOL_KEYS = {"name", "language", "source_file"}


# ---------------------------------------------------------------------------
# parse_requirements_txt
# ---------------------------------------------------------------------------


def test_req_pinned_version(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("pandas==2.0.3\n")
    tools = parse_requirements_txt(f)
    assert tools[0]["name"] == "pandas"
    assert tools[0]["version"] == "2.0.3"


def test_req_ge_version(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("requests>=2.28.0\n")
    tools = parse_requirements_txt(f)
    assert tools[0]["name"] == "requests"
    assert tools[0]["version"] == "2.28.0"


def test_req_skips_comments(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("# comment\npandas==2.0.3\n")
    tools = parse_requirements_txt(f)
    assert len(tools) == 1


def test_req_skips_option_lines(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("-r base.txt\npandas==2.0.3\n")
    tools = parse_requirements_txt(f)
    assert len(tools) == 1


def test_req_language_python(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("scipy==1.11.1\n")
    assert parse_requirements_txt(f)[0]["language"] == "python"


def test_req_source_pypi(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("numpy==1.24.3\n")
    assert parse_requirements_txt(f)[0]["source"] == "PyPI"


def test_req_multiple_packages(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("pandas==2.0.3\nnumpy==1.24.3\nscipy==1.11.1\n")
    assert len(parse_requirements_txt(f)) == 3


def test_req_source_file_name(tmp_path):
    f = tmp_path / "requirements-dev.txt"
    f.write_text("pytest==7.4.0\n")
    tools = parse_requirements_txt(f)
    assert tools[0]["source_file"] == "requirements-dev.txt"


# ---------------------------------------------------------------------------
# parse_renv_lock
# ---------------------------------------------------------------------------

RENV_LOCK = json.dumps({
    "R": {"Version": "4.3.2"},
    "Packages": {
        "ggplot2": {"Package": "ggplot2", "Version": "3.4.2", "Source": "CRAN"},
        "DESeq2":  {"Package": "DESeq2",  "Version": "1.40.2", "Source": "Bioconductor"},
    },
})


def test_renv_r_version(tmp_path):
    f = tmp_path / "renv.lock"
    f.write_text(RENV_LOCK)
    _, r_version, _ = parse_renv_lock(f)
    assert r_version == "4.3.2"


def test_renv_package_names(tmp_path):
    f = tmp_path / "renv.lock"
    f.write_text(RENV_LOCK)
    tools, _, _ = parse_renv_lock(f)
    names = {t["name"] for t in tools}
    assert "ggplot2" in names
    assert "DESeq2" in names


def test_renv_versions(tmp_path):
    f = tmp_path / "renv.lock"
    f.write_text(RENV_LOCK)
    tools, _, _ = parse_renv_lock(f)
    gg = next(t for t in tools if t["name"] == "ggplot2")
    assert gg["version"] == "3.4.2"


def test_renv_language_r(tmp_path):
    f = tmp_path / "renv.lock"
    f.write_text(RENV_LOCK)
    tools, _, _ = parse_renv_lock(f)
    assert all(t["language"] == "r" for t in tools)


def test_renv_source_field(tmp_path):
    f = tmp_path / "renv.lock"
    f.write_text(RENV_LOCK)
    tools, _, _ = parse_renv_lock(f)
    gg = next(t for t in tools if t["name"] == "ggplot2")
    assert gg["source"] == "CRAN"
    de = next(t for t in tools if t["name"] == "DESeq2")
    assert de["source"] == "Bioconductor"


def test_renv_malformed_returns_empty(tmp_path):
    f = tmp_path / "renv.lock"
    f.write_text("not json {{{")
    tools, r_ver, _ = parse_renv_lock(f)
    assert tools == []
    assert r_ver is None


# ---------------------------------------------------------------------------
# parse_conda_yaml
# ---------------------------------------------------------------------------

CONDA_YAML = """\
name: myenv
channels:
  - conda-forge
dependencies:
  - python=3.10.0
  - numpy=1.24.3
  - samtools=1.17
"""


def test_conda_deps(tmp_path):
    f = tmp_path / "environment.yaml"
    f.write_text(CONDA_YAML)
    tools, _ = parse_conda_yaml(f)
    names = {t["name"] for t in tools}
    assert "numpy" in names
    assert "samtools" in names


def test_conda_python_version(tmp_path):
    f = tmp_path / "environment.yaml"
    f.write_text(CONDA_YAML)
    _, pv = parse_conda_yaml(f)
    assert pv == "3.10.0"


def test_conda_version_captured(tmp_path):
    f = tmp_path / "environment.yaml"
    f.write_text(CONDA_YAML)
    tools, _ = parse_conda_yaml(f)
    numpy_t = next(t for t in tools if t["name"] == "numpy")
    assert numpy_t["version"] == "1.24.3"


def test_conda_source_conda(tmp_path):
    f = tmp_path / "environment.yaml"
    f.write_text(CONDA_YAML)
    tools, _ = parse_conda_yaml(f)
    for t in tools:
        assert t["source"] == "conda"


# ---------------------------------------------------------------------------
# scan_directory — fixture-based
# ---------------------------------------------------------------------------


def test_scan_py_project_tools():
    result = scan_directory(FIXTURES / "py_project")
    names = {t["name"] for t in result["tools"]}
    assert "pandas" in names
    assert "scipy" in names


def test_scan_py_project_lockfile_found():
    result = scan_directory(FIXTURES / "py_project")
    assert any("requirements.txt" in lf for lf in result["lockfiles_found"])


def test_scan_r_project_tools():
    result = scan_directory(FIXTURES / "r_project")
    names = {t["name"] for t in result["tools"]}
    assert "ggplot2" in names
    assert "DESeq2" in names


def test_scan_r_version():
    result = scan_directory(FIXTURES / "r_project")
    assert result["r_version"] == "4.3.2"


def test_scan_finds_meta_json():
    result = scan_directory(FIXTURES / "py_project")
    assert len(result["artifacts"]) >= 1


def test_scan_artifact_sha256():
    result = scan_directory(FIXTURES / "py_project")
    art = result["artifacts"][0]
    assert art["sha256"] is not None
    assert len(art["sha256"]) == 64
    assert all(c in "0123456789abcdef" for c in art["sha256"])


def test_scan_artifact_doi():
    result = scan_directory(FIXTURES / "py_project")
    art = result["artifacts"][0]
    assert art["doi"] == "10.1093/nar/gkv1145"


def test_scan_artifact_source_url():
    result = scan_directory(FIXTURES / "py_project")
    art = result["artifacts"][0]
    assert art["source_url"] is not None
    assert art["source_url"].startswith("https://")


def test_scan_artifact_data_version():
    result = scan_directory(FIXTURES / "py_project")
    art = result["artifacts"][0]
    assert art["data_version"] == "2026-05-01"


def test_scan_artifact_fetched_at():
    result = scan_directory(FIXTURES / "py_project")
    art = result["artifacts"][0]
    assert art["fetched_at"] == "2026-05-01T14:23:00Z"


def test_scan_artifact_params():
    result = scan_directory(FIXTURES / "py_project")
    art = result["artifacts"][0]
    assert art["params"] == {"species": "human", "aspect": "BP"}


def test_scan_snakemake_workflow():
    result = scan_directory(FIXTURES / "snakemake_project")
    assert any("Snakefile" in w for w in result["workflows"])


def test_scan_conda_yaml():
    result = scan_directory(FIXTURES / "snakemake_project")
    names = {t["name"] for t in result["tools"]}
    assert "pandas" in names
    assert "snakemake" in names


def test_scan_conda_python_version():
    result = scan_directory(FIXTURES / "snakemake_project")
    assert result["python_version"] == "3.10.0"


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


def test_schema_keys():
    result = scan_directory(FIXTURES / "py_project")
    missing = SCHEMA_KEYS - set(result)
    assert not missing, f"missing schema keys: {missing}"


def test_tools_have_required_fields():
    result = scan_directory(FIXTURES / "py_project")
    for t in result["tools"]:
        missing = TOOL_KEYS - set(t)
        assert not missing, f"tool {t} missing fields: {missing}"


def test_deduplication():
    result = scan_directory(FIXTURES / "py_project")
    seen: set[tuple] = set()
    for t in result["tools"]:
        key = (t.get("name"), t.get("version"), t.get("language"))
        assert key not in seen, f"duplicate tool entry: {key}"
        seen.add(key)


def test_scan_root_is_absolute():
    result = scan_directory(FIXTURES / "py_project")
    assert Path(result["scan_root"]).is_absolute()


def test_artifacts_schema():
    result = scan_directory(FIXTURES / "py_project")
    for art in result["artifacts"]:
        for key in ("file", "meta_file", "sha256", "stamped_at", "fetched_at",
                    "source_url", "doi", "data_version", "params"):
            assert key in art, f"artifact missing key: {key}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_writes_json(tmp_path):
    from scan import main
    out = tmp_path / "out.json"
    rc = main([str(FIXTURES / "py_project"), "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert "tools" in data
    assert "artifacts" in data


def test_cli_stdout(capsys):
    from scan import main
    rc = main([str(FIXTURES / "r_project")])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "tools" in data


def test_cli_missing_directory(tmp_path):
    from scan import main
    rc = main([str(tmp_path / "nonexistent")])
    assert rc == 1

"""Tests for the CSV merger's data paths and enrichment."""

import csv
import json

from source_lab.pipeline.merge_csvs import ANALYSIS_DIR, REPO_ROOT, SOURCES_DIR, merge_extension_csvs


# @lat: [[source-tests#CSV merge#Explicit directories]]
def test_merge_uses_explicit_directories(tmp_path):
    sources = tmp_path / "sources"
    analysis = tmp_path / "analysis"
    (analysis / "owner__repo").mkdir(parents=True)
    sources.mkdir()

    (sources / "browser-extension-repos.csv").write_text(
        "repo_url,repo_name,category\n"
        "https://github.com/owner/repo,repo,Testing\n",
        encoding="utf-8",
    )
    (sources / "browser-extensions.csv").write_text(
        "Category,Extension,Repo Link,Description\n",
        encoding="utf-8",
    )
    (analysis / "owner__repo" / "manifest-analysis.json").write_text(
        json.dumps(
            {
                "repo": "owner/repo",
                "manifest_version": 3,
                "permissions": ["tabs"],
                "content_scripts": {"matches": ["<all_urls>"]},
                "background": "service_worker",
                "risk_level": "LOW",
                "heuristic_score": 2,
            }
        ),
        encoding="utf-8",
    )

    merge_extension_csvs(sources, analysis)

    merged = sources / "browser-extensions-merged.csv"
    mirror = sources / "browser-extension-sources.csv"
    assert merged.is_file()
    assert mirror.is_file()

    with merged.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["repo_name"] == "owner/repo"
    assert rows[0]["permissions"] == "tabs"
    assert rows[0]["content_script_matches"] == "<all_urls>"
    assert rows[0]["analysis_status"] == "ANALYZED"


# @lat: [[source-tests#CSV merge#Default data paths]]
def test_default_directories_point_at_shared_resources():
    from source_lab.paths import Paths
    paths = Paths.from_env()
    assert SOURCES_DIR == paths.resources / "sources"
    assert ANALYSIS_DIR == paths.storage / "analysis"
    assert REPO_ROOT.name == "source-lab"
    # Resource trees are operator supplied, never assumed to be bundled.

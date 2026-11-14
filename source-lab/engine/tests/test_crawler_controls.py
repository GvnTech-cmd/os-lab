"""Offline list parsing, bounded retries and cancellation acceptance."""
import argparse
import logging
import threading
import zipfile

import pytest
from source_lab.pipeline.ext_repo_analyzer import load_targets, retry_call, StopRequested


@pytest.mark.parametrize("extension", ["txt", "csv", "xlsx"])
def test_operator_lists_parse_without_network(tmp_path, extension):
    path = tmp_path / ("owned." + extension)
    if extension == "txt":
        path.write_text("owned/sample\nowned/sample # duplicate\n")
    elif extension == "csv":
        path.write_text("repo_url\nhttps://github.com/owned/sample\nhttps://github.com/owned/sample\n")
    else:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("xl/worksheets/sheet1.xml", '<worksheet><sheetData><row><c t="inlineStr"><is><t>repo</t></is></c></row><row><c t="inlineStr"><is><t>owned/sample</t></is></c></row></sheetData></worksheet>')
    targets = load_targets(argparse.Namespace(scan_dir=None, repos=[], input=str(path)), logging.getLogger("owned"))
    assert len(targets) == 1 and targets[0].spec == "owned/sample"


def test_retries_are_bounded_and_stop_interrupts_backoff():
    event = threading.Event()
    calls = []
    def failing():
        calls.append(1)
        raise OSError("owned fixture failure")
    kwargs = dict(what="owned", attempts=2, base_delay=0, max_delay=0, logger=logging.getLogger("owned"), stop_event=event, retry_on=(OSError,))
    with pytest.raises(OSError):
        retry_call(failing, **kwargs)
    assert len(calls) == 2
    event.set()
    with pytest.raises(StopRequested):
        retry_call(failing, **kwargs)
    assert len(calls) == 2


def test_fault_isolated_stage_preserves_other_artifacts(tmp_path, monkeypatch):
    import json
    import sys
    from source_lab.pipeline import ext_repo_analyzer as crawler
    target = tmp_path / "owned"
    target.mkdir()
    (target / "manifest.json").write_text('{"manifest_version":3,"name":"Owned","version":"1","permissions":["tabs"]}')
    (target / "owned.js").write_text('console.log("owned")')
    def broken(*args, **kwargs):
        raise ValueError("owned injected stage failure")
    monkeypatch.setattr(crawler, "parse_dependencies", broken)
    output = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["crawler", str(target), "--out-dir", str(output), "--no-metadata", "--no-ast", "--no-map", "--no-color"])
    assert crawler.main() == 1
    assert (output / "local__owned/manifest-analysis.json").is_file()
    assert (output / "local__owned/file-tree.json").is_file()
    report = json.loads((output / "report.json").read_text())
    assert report["results"][0]["status"] != "OK"

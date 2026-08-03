"""Integration tests for the host-list analysis flow."""

from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pytest

from src.cli import collect_sources, update_readme
from src.config import SourceConfig, Whitelist
from src.fetcher import FetchedSource, FetchError
from src.pipeline import ContributionStats, PipelineFiles, process_annotated_pipeline
from src.state_manager import AnalysisState


def _fetch_result(content: str, destination: Path) -> FetchedSource:
    destination.write_text(content)
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return FetchedSource(
        content_hash=content_hash,
        path=destination,
        byte_count=len(content.encode()),
        line_count=len(content.splitlines()),
        final_url="https://example.com/list",
    )


def test_sources_flow_through_normalization_provenance_and_whitelist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fetched source data should produce effective per-source contribution metrics."""
    sources = [
        SourceConfig(name="General A", url="https://example.com/a"),
        SourceConfig(name="General B", url="https://example.com/b"),
        SourceConfig(name="NSFW", url="https://example.com/nsfw", nsfw=True),
    ]
    content_by_url = {
        sources[0].url: "shared.example\na-only.example\nallowed.example\n",
        sources[1].url: "0.0.0.0 shared.example\nb-only.example\n",
        sources[2].url: "||adult.example^\na-only.example\n",
    }
    monkeypatch.setattr(
        "src.cli.fetch_url_with_hash",
        lambda url, destination, **_kwargs: _fetch_result(content_by_url[url], destination),
    )
    state = AnalysisState()
    pipeline = PipelineFiles.create(tmp_path)

    source_stats, id_to_name, changed, failures = collect_sources(
        sources,
        pipeline.annotated,
        state,
    )
    all_count, general_count, contributions, whitelisted_count = process_annotated_pipeline(
        pipeline,
        id_to_name,
        Whitelist(exact={"allowed.example"}),
        quiet=True,
    )

    assert failures == []
    assert changed is True
    assert source_stats == {"General A": 3, "General B": 2, "NSFW": 2}
    assert (all_count, general_count, whitelisted_count) == (4, 3, 1)
    assert contributions.contrib_general == {"General A": 1, "General B": 1, "NSFW": 0}
    assert contributions.contrib_all == {"General A": 0, "General B": 1, "NSFW": 1}


def test_fetch_failure_is_reported_for_analysis_abort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed source must be reported instead of producing partial analytics."""
    source = SourceConfig(name="Unavailable", url="https://example.com/down")
    monkeypatch.setattr(
        "src.cli.fetch_url_with_hash",
        lambda _url, _destination, **_kwargs: (_ for _ in ()).throw(FetchError("network failure")),
    )

    stats, _, changed, failures = collect_sources(
        [source],
        PipelineFiles.create(tmp_path).annotated,
        AnalysisState(),
    )

    assert stats == {"Unavailable": 0}
    assert changed is False
    assert failures == ["Unavailable"]


def test_readme_reports_removal_candidate_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """README output should expose candidacy and its concrete reasons."""
    monkeypatch.chdir(tmp_path)
    Path("README.md").write_text("Header\n<!-- STATS_START -->old<!-- STATS_END -->\n")
    sources = [
        SourceConfig(name="Keep", url="https://example.com/keep"),
        SourceConfig(name="Candidate", url="https://example.com/candidate"),
    ]
    contributions = ContributionStats(
        contrib_all={"Keep": 51, "Candidate": 1},
        contrib_general={"Keep": 51, "Candidate": 1},
    )

    update_readme(
        sources,
        {"Keep": 100, "Candidate": 5},
        100,
        100,
        contributions,
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        {"Candidate": 30},
    )

    readme = Path("README.md").read_text()
    assert "<th>Removal Candidate</th>" in readme
    assert "<td>51</td><td>No</td>" in readme
    assert "<strong>Yes</strong> — 1 unique domain; unchanged 30 days" in readme


def test_readme_escapes_configuration_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuration values cannot break generated HTML attributes or elements."""
    monkeypatch.chdir(tmp_path)
    Path("README.md").write_text("Header\n<!-- STATS_START -->old<!-- STATS_END -->\n")
    source = SourceConfig(
        name='<script>alert("x")</script>',
        url="https://example.com/?a=1&b=2",
    )

    update_readme(
        [source],
        {source.name: 1},
        1,
        1,
        ContributionStats(
            contrib_all={source.name: 1},
            contrib_general={source.name: 1},
        ),
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        {},
    )

    readme = Path("README.md").read_text()
    assert "<script>" not in readme
    assert "&lt;script&gt;" in readme
    assert 'href="https://example.com/?a=1&amp;b=2"' in readme

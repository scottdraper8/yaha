"""Integration tests for YAHA.

End-to-end tests using real HTTP requests and full pipeline.
"""

from datetime import UTC, datetime
from pathlib import Path
import subprocess

from src.config import SourceConfig, Whitelist, load_whitelist
from src.domain_processor import extract_domains_from_lines
from src.fetcher import fetch_url_with_hash
from src.hosts_generator import generate_hosts_file_from_file
from src.pipeline import PipelineFiles, process_annotated_pipeline
from src.state_manager import CompilationState, load_state, save_state, update_source_state


class TestEndToEndPipeline:
    """End-to-end integration tests."""

    def test_fetch_and_parse_real_blocklist(self) -> None:
        """Test fetching and parsing a real blocklist."""
        url = "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn/hosts"

        content_hash, lines = fetch_url_with_hash(url, timeout=60)

        assert len(content_hash) == 64

        domains = list(extract_domains_from_lines(lines))

        assert len(domains) > 0

    def test_full_pipeline_deduplication(self, tmp_path: Path) -> None:
        """Test full pipeline with deduplication."""
        pipeline = PipelineFiles.create(tmp_path)
        id_to_name = {0: "General", 1: "Other"}
        whitelist = Whitelist()

        # Shared domain + unique domains
        pipeline.annotated.write_text("shared.com\t0\t1\nshared.com\t1\t1\nunique.com\t0\t1\n")

        all_count, _general_count, stats, _ = process_annotated_pipeline(
            pipeline, id_to_name, whitelist, quiet=True
        )

        assert all_count == 2  # shared + unique
        assert stats.contrib_all["General"] == 1  # unique.com

        pipeline.cleanup()

    def test_hosts_file_generation(self, tmp_path: Path) -> None:
        """Test generating hosts file from pipeline output."""
        (tmp_path / "blocklists").mkdir()

        pipeline = PipelineFiles.create(tmp_path)
        id_to_name = {0: "Source"}
        whitelist = Whitelist()

        pipeline.annotated.write_text("example.com\t0\t1\n")

        process_annotated_pipeline(pipeline, id_to_name, whitelist, quiet=True)

        hosts_path = tmp_path / "blocklists" / "hosts"
        header = ["# YAHA Test"]
        generate_hosts_file_from_file(pipeline.domains_all, hosts_path, header)

        content = hosts_path.read_text()
        assert "0.0.0.0 example.com" in content

        pipeline.cleanup()

    def test_state_persistence_roundtrip(self, tmp_path: Path) -> None:
        """Test state survives save/load cycle."""
        state_path = tmp_path / "state.json"
        source = SourceConfig(name="Test", url="https://example.com")
        state = CompilationState()

        now = datetime.now(UTC)
        update_source_state(state, source, "hash123", now)
        state.compilation_count = 5
        save_state(state, state_path)

        loaded = load_state(state_path)

        assert loaded.compilation_count == 5
        assert loaded.sources["Test"].content_hash == "hash123"

    def test_whitelist_filtering(self, tmp_path: Path) -> None:
        """Test whitelist filtering in pipeline."""
        whitelist_path = tmp_path / "whitelist.txt"
        whitelist_path.write_text("blocked.com\n")

        whitelist = load_whitelist(whitelist_path)

        pipeline = PipelineFiles.create(tmp_path)
        id_to_name = {0: "Source"}

        pipeline.annotated.write_text("blocked.com\t0\t1\nallowed.com\t0\t1\n")

        all_count, _, _, whitelisted_count = process_annotated_pipeline(
            pipeline, id_to_name, whitelist, quiet=True
        )

        assert all_count == 1
        assert whitelisted_count == 1

        pipeline.cleanup()


class TestCLIArguments:
    """Test CLI argument handling."""

    def test_main_help(self) -> None:
        """Test --help argument works."""
        result = subprocess.run(
            ["poetry", "run", "python", "-m", "src.cli", "--help"],
            capture_output=True,
            text=True,
            cwd="/home/scott/Repos/yaha",
            check=False,
        )

        assert result.returncode == 0
        assert "YAHA" in result.stdout
        assert "--force" in result.stdout

"""Tests for src/pipeline.py.

Tests the core deduplication and contribution tracking logic.
Whitelist tests are in test_config.py (single source of truth).
"""

from pathlib import Path

from src.config import Whitelist
from src.pipeline import PipelineFiles, process_annotated_pipeline


class TestPipelineFiles:
    """Tests for PipelineFiles - minimal, just cleanup behavior."""

    def test_cleanup_removes_files(self, tmp_path: Path) -> None:
        """Test cleanup removes all temp files."""
        files = PipelineFiles.create(tmp_path)

        for f in [files.annotated, files.sorted]:
            f.touch()

        files.cleanup()

        assert not any(f.exists() for f in [files.annotated, files.sorted])

    def test_cleanup_handles_missing_files(self, tmp_path: Path) -> None:
        """Test cleanup doesn't raise if files don't exist."""
        files = PipelineFiles.create(tmp_path)
        files.cleanup()


class TestProcessAnnotatedPipeline:
    """Tests for process_annotated_pipeline - core deduplication logic."""

    def test_deduplication(self, tmp_path: Path) -> None:
        """Test domains appearing in multiple sources are deduplicated."""
        files = PipelineFiles.create(tmp_path)
        id_to_name = {0: "Source1", 1: "Source2"}
        whitelist = Whitelist()

        files.annotated.write_text("example.com\t0\t1\nexample.com\t1\t1\nother.com\t0\t1\n")

        all_count, general_count, _, _ = process_annotated_pipeline(
            files, id_to_name, whitelist, quiet=True
        )

        assert all_count == 2
        assert general_count == 2
        files.cleanup()

    def test_contribution_stats(self, tmp_path: Path) -> None:
        """Test unique contribution tracking per source."""
        files = PipelineFiles.create(tmp_path)
        id_to_name = {0: "Source1", 1: "Source2"}
        whitelist = Whitelist()

        files.annotated.write_text(
            "shared.com\t0\t1\nshared.com\t1\t1\nunique1.com\t0\t1\nunique2.com\t1\t1\n"
        )

        _, _, stats, _ = process_annotated_pipeline(files, id_to_name, whitelist, quiet=True)

        assert stats.contrib_all["Source1"] == 1
        assert stats.contrib_all["Source2"] == 1
        files.cleanup()

    def test_category_separation(self, tmp_path: Path) -> None:
        """Test general (1) vs non-general (0) category separation."""
        files = PipelineFiles.create(tmp_path)
        id_to_name = {0: "General", 1: "Other"}
        whitelist = Whitelist()

        files.annotated.write_text("general.com\t0\t1\nother.com\t1\t0\n")

        all_count, general_count, _, _ = process_annotated_pipeline(
            files, id_to_name, whitelist, quiet=True
        )

        assert all_count == 2
        assert general_count == 1
        files.cleanup()

    def test_whitelist_filtering(self, tmp_path: Path) -> None:
        """Test whitelisted domains are excluded."""
        files = PipelineFiles.create(tmp_path)
        id_to_name = {0: "Source1"}
        whitelist = Whitelist(exact={"blocked.com"}, wildcards=["*.safe.org"])

        files.annotated.write_text("blocked.com\t0\t1\nsub.safe.org\t0\t1\nallowed.com\t0\t1\n")

        all_count, _, _, whitelisted_count = process_annotated_pipeline(
            files, id_to_name, whitelist, quiet=True
        )

        assert all_count == 1
        assert whitelisted_count == 2
        files.cleanup()

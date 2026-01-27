"""Tests for src/hosts_generator.py.

Minimal tests for file I/O logic. This module is intentionally simple.
"""

from pathlib import Path

from src.hosts_generator import generate_hosts_file, generate_hosts_file_from_file


class TestGenerateHostsFile:
    """Tests for generate_hosts_file - file I/O logic."""

    def test_writes_header_and_domains(self, tmp_path: Path) -> None:
        """Test basic hosts file generation."""
        output = tmp_path / "hosts"
        header = ["# Header line"]
        domains = iter(["example.com", "test.org"])

        count = generate_hosts_file(domains, output, header)

        assert count == 2
        content = output.read_text()
        assert content.startswith("# Header line\n\n")
        assert "0.0.0.0 example.com\n" in content
        assert "0.0.0.0 test.org\n" in content

    def test_skips_empty_domains(self, tmp_path: Path) -> None:
        """Test empty/whitespace domains are skipped."""
        output = tmp_path / "hosts"
        domains = iter(["valid.com", "", "   ", "also-valid.com"])

        count = generate_hosts_file(domains, output, ["# Test"])

        assert count == 2


class TestGenerateHostsFileFromFile:
    """Tests for generate_hosts_file_from_file."""

    def test_reads_from_file(self, tmp_path: Path) -> None:
        """Test reading domains from source file."""
        source = tmp_path / "domains.txt"
        output = tmp_path / "hosts"

        source.write_text("example.com\ntest.org\n")

        count = generate_hosts_file_from_file(source, output, ["# Header"])

        assert count == 2
        assert "0.0.0.0 example.com" in output.read_text()

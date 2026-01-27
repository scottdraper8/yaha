"""Pytest fixtures for YAHA test suite."""

from pathlib import Path

import pytest


@pytest.fixture
def sample_psl_content() -> str:
    """Return minimal PSL content for testing."""
    return """// Test Public Suffix List
com
net
org
co.uk
github.io
*.ck
!www.ck
"""


@pytest.fixture
def sample_psl(tmp_path: Path, sample_psl_content: str) -> Path:
    """Create minimal PSL file for testing."""
    psl_file = tmp_path / "test_psl.dat"
    psl_file.write_text(sample_psl_content)
    return psl_file


@pytest.fixture
def sample_blocklists_json() -> str:
    """Return sample blocklists.json content."""
    return """[
    {"name": "Test List 1", "url": "https://example.com/list1.txt"},
    {"name": "Test List 2", "url": "https://example.com/list2.txt", "nsfw": false},
    {"name": "NSFW List", "url": "https://example.com/nsfw.txt", "nsfw": true}
]"""


@pytest.fixture
def sample_whitelist_content() -> str:
    """Return sample whitelist content."""
    return """# Whitelist
example.com
safe-domain.org
*.whitelisted.com
"""

"""Pytest fixtures for YAHA test suite."""

import pytest


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

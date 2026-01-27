"""Tests for src/domain_processor.py."""

from pathlib import Path

import pytest

from src.domain_processor import (
    PublicSuffixList,
    extract_domains_from_lines,
    get_registrable_domain,
    is_valid_domain,
    load_public_suffix_list,
)


class TestPublicSuffixListLoading:
    """Tests for PSL loading and parsing."""

    def test_load_basic_psl(self, sample_psl: Path) -> None:
        """Test loading basic PSL file."""
        psl = load_public_suffix_list(sample_psl)

        assert "com" in psl.exact
        assert "net" in psl.exact
        assert "org" in psl.exact
        assert "co.uk" in psl.exact
        assert "github.io" in psl.exact

    def test_load_wildcard_rules(self, sample_psl: Path) -> None:
        """Test loading wildcard rules from PSL."""
        psl = load_public_suffix_list(sample_psl)

        assert "ck" in psl.wildcards

    def test_load_exception_rules(self, sample_psl: Path) -> None:
        """Test loading exception rules from PSL."""
        psl = load_public_suffix_list(sample_psl)

        assert "www.ck" in psl.exceptions

    def test_ignores_comments(self, sample_psl: Path) -> None:
        """Test that comments are ignored."""
        psl = load_public_suffix_list(sample_psl)

        # Comments should not appear in any set
        assert "Test Public Suffix List" not in psl.exact
        assert "Comments are ignored" not in psl.exact


class TestGetRegistrableDomain:
    """Tests for get_registrable_domain function."""

    @pytest.fixture
    def psl(self, sample_psl: Path) -> PublicSuffixList:
        """Load PSL for testing."""
        return load_public_suffix_list(sample_psl)

    def test_simple_domain(self, psl: PublicSuffixList) -> None:
        """Test stripping www from simple domain."""
        assert get_registrable_domain("www.example.com", psl) == "example.com"

    def test_multi_subdomain(self, psl: PublicSuffixList) -> None:
        """Test stripping multiple subdomains."""
        assert get_registrable_domain("a.b.c.example.com", psl) == "example.com"

    def test_public_suffix_service(self, psl: PublicSuffixList) -> None:
        """Test preserving registrable domain for public suffix services."""
        assert get_registrable_domain("user.github.io", psl) == "user.github.io"
        assert get_registrable_domain("api.user.github.io", psl) == "user.github.io"

    def test_multi_level_suffix(self, psl: PublicSuffixList) -> None:
        """Test multi-level public suffixes like co.uk."""
        assert get_registrable_domain("www.example.co.uk", psl) == "example.co.uk"
        assert get_registrable_domain("sub.sub.example.co.uk", psl) == "example.co.uk"

    def test_wildcard_rule(self, psl: PublicSuffixList) -> None:
        """Test wildcard rule handling (*.ck)."""
        # *.ck means any X.ck is a public suffix
        # For sub.example.ck: public suffix is example.ck (wildcard match)
        # Registrable domain = public suffix + one label = sub.example.ck
        assert get_registrable_domain("sub.example.ck", psl) == "sub.example.ck"
        # For example.ck: the domain IS the public suffix, so return as-is
        assert get_registrable_domain("example.ck", psl) == "example.ck"

    def test_exception_to_wildcard(self, psl: PublicSuffixList) -> None:
        """Test exception rule (!www.ck)."""
        # !www.ck means www.ck is NOT a public suffix (exception to *.ck)
        # Without the exception, *.ck would make www.ck a public suffix
        # With the exception, www.ck is the registrable domain (TLD is ck)
        assert get_registrable_domain("www.ck", psl) == "www.ck"
        # For sub.www.ck: www.ck is registrable due to exception
        # So registrable domain = www.ck
        assert get_registrable_domain("sub.www.ck", psl) == "www.ck"

    def test_single_label_domain(self, psl: PublicSuffixList) -> None:
        """Test single-label domain returns unchanged."""
        assert get_registrable_domain("localhost", psl) == "localhost"

    def test_domain_is_public_suffix(self, psl: PublicSuffixList) -> None:
        """Test when domain is exactly a public suffix."""
        assert get_registrable_domain("com", psl) == "com"
        assert get_registrable_domain("co.uk", psl) == "co.uk"


class TestIsValidDomain:
    """Tests for is_valid_domain function."""

    def test_valid_simple_domain(self) -> None:
        """Test valid simple domains."""
        assert is_valid_domain("example.com") is True
        assert is_valid_domain("sub.example.com") is True
        assert is_valid_domain("a-b-c.example.com") is True

    def test_valid_long_domain(self) -> None:
        """Test valid domain at max label length."""
        long_label = "a" * 63
        assert is_valid_domain(f"{long_label}.com") is True

    def test_invalid_empty(self) -> None:
        """Test empty string is invalid."""
        assert is_valid_domain("") is False

    def test_invalid_too_long(self) -> None:
        """Test domain exceeding 253 chars is invalid."""
        long_domain = "a" * 254
        assert is_valid_domain(long_domain) is False

    def test_invalid_no_tld(self) -> None:
        """Test single-label domain is invalid."""
        assert is_valid_domain("localhost") is False

    def test_invalid_leading_dot(self) -> None:
        """Test leading dot is invalid."""
        assert is_valid_domain(".example.com") is False

    def test_invalid_trailing_dot(self) -> None:
        """Test trailing dot is invalid."""
        assert is_valid_domain("example.com.") is False

    def test_invalid_double_dot(self) -> None:
        """Test double dots are invalid."""
        assert is_valid_domain("example..com") is False

    def test_invalid_long_label(self) -> None:
        """Test label exceeding 63 chars is invalid."""
        long_label = "a" * 64
        assert is_valid_domain(f"{long_label}.com") is False

    def test_invalid_leading_hyphen(self) -> None:
        """Test leading hyphen in label is invalid."""
        assert is_valid_domain("-example.com") is False

    def test_invalid_trailing_hyphen(self) -> None:
        """Test trailing hyphen in label is invalid."""
        assert is_valid_domain("example-.com") is False

    def test_valid_hyphen_in_middle(self) -> None:
        """Test hyphen in middle of label is valid."""
        assert is_valid_domain("ex-ample.com") is True
        assert is_valid_domain("my-domain-name.org") is True


class TestExtractDomainsFromLines:
    """Tests for extract_domains_from_lines function."""

    @pytest.fixture
    def psl(self, sample_psl: Path) -> PublicSuffixList:
        """Load PSL for testing."""
        return load_public_suffix_list(sample_psl)

    def test_hosts_format(self, psl: PublicSuffixList) -> None:
        """Test extracting domains from hosts file format."""
        lines = iter(
            [
                "0.0.0.0 ads.example.com",
                "127.0.0.1 tracker.example.org",
                "::1 malware.bad.net",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        assert "example.com" in domains
        assert "example.org" in domains
        assert "bad.net" in domains

    def test_raw_domain_format(self, psl: PublicSuffixList) -> None:
        """Test extracting from raw domain list."""
        lines = iter(
            [
                "ads.example.com",
                "tracker.example.org",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        assert "example.com" in domains
        assert "example.org" in domains

    def test_adblock_format(self, psl: PublicSuffixList) -> None:
        """Test extracting from Adblock Plus format."""
        lines = iter(
            [
                "||ads.example.com^",
                "||tracker.example.org^",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        assert "example.com" in domains
        assert "example.org" in domains

    def test_ignores_comments(self, psl: PublicSuffixList) -> None:
        """Test that comments are ignored."""
        lines = iter(
            [
                "# This is a comment",
                "! Adblock comment",
                "[Adblock Plus 2.0]",
                "ads.example.com",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        assert len(domains) == 1
        assert "example.com" in domains

    def test_ignores_localhost(self, psl: PublicSuffixList) -> None:
        """Test that localhost entries are ignored."""
        lines = iter(
            [
                "127.0.0.1 localhost",
                "::1 localhost",
                "0.0.0.0 localhost",
                "::1 ip6-localhost",
                "0.0.0.0 ads.example.com",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        assert len(domains) == 1
        assert "example.com" in domains

    def test_ignores_empty_lines(self, psl: PublicSuffixList) -> None:
        """Test that empty lines are ignored."""
        lines = iter(
            [
                "",
                "   ",
                "ads.example.com",
                "",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        assert len(domains) == 1

    def test_mixed_formats(self, psl: PublicSuffixList) -> None:
        """Test handling mixed formats in same stream."""
        lines = iter(
            [
                "# Comment",
                "0.0.0.0 ads.example.com",
                "tracker.example.org",
                "||malware.bad.net^",
                "",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        assert len(domains) == 3

    def test_strips_to_base_domain(self, psl: PublicSuffixList) -> None:
        """Test that subdomains are stripped to base domain."""
        lines = iter(
            [
                "www.example.com",
                "api.sub.example.com",
                "cdn.example.com",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        # All should resolve to example.com
        assert all(d == "example.com" for d in domains)

    def test_preserves_public_suffix_domains(self, psl: PublicSuffixList) -> None:
        """Test that public suffix domains are preserved correctly."""
        lines = iter(
            [
                "user.github.io",
                "api.user.github.io",
            ]
        )
        domains = list(extract_domains_from_lines(lines, psl))

        assert all(d == "user.github.io" for d in domains)

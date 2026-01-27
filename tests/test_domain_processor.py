"""Tests for src/domain_processor.py."""

from src.domain_processor import (
    extract_domains_from_lines,
    is_valid_domain,
)


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

    def test_hosts_format(self) -> None:
        """Test extracting domains from hosts file format."""
        lines = iter(
            [
                "0.0.0.0 ads.example.com",
                "127.0.0.1 tracker.example.org",
                "::1 malware.bad.net",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert "ads.example.com" in domains
        assert "tracker.example.org" in domains
        assert "malware.bad.net" in domains

    def test_raw_domain_format(self) -> None:
        """Test extracting from raw domain list."""
        lines = iter(
            [
                "ads.example.com",
                "tracker.example.org",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert "ads.example.com" in domains
        assert "tracker.example.org" in domains

    def test_adblock_format(self) -> None:
        """Test extracting from Adblock Plus format."""
        lines = iter(
            [
                "||ads.example.com^",
                "||tracker.example.org^",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert "ads.example.com" in domains
        assert "tracker.example.org" in domains

    def test_ignores_comments(self) -> None:
        """Test that comments are ignored."""
        lines = iter(
            [
                "# This is a comment",
                "! Adblock comment",
                "[Adblock Plus 2.0]",
                "ads.example.com",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert len(domains) == 1
        assert "ads.example.com" in domains

    def test_ignores_localhost(self) -> None:
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
        domains = list(extract_domains_from_lines(lines))

        assert len(domains) == 1
        assert "ads.example.com" in domains

    def test_ignores_empty_lines(self) -> None:
        """Test that empty lines are ignored."""
        lines = iter(
            [
                "",
                "   ",
                "ads.example.com",
                "",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert len(domains) == 1

    def test_mixed_formats(self) -> None:
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
        domains = list(extract_domains_from_lines(lines))

        assert len(domains) == 3

    def test_preserves_exact_domains(self) -> None:
        """Test that domains are preserved exactly as specified."""
        lines = iter(
            [
                "www.example.com",
                "api.sub.example.com",
                "cdn.example.com",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert domains == ["www.example.com", "api.sub.example.com", "cdn.example.com"]

    def test_preserves_subdomain_structure(self) -> None:
        """Test that subdomain structure is preserved."""
        lines = iter(
            [
                "user.github.io",
                "api.user.github.io",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert domains == ["user.github.io", "api.user.github.io"]

    def test_lowercases_domains(self) -> None:
        """Test that domains are lowercased."""
        lines = iter(
            [
                "WWW.EXAMPLE.COM",
                "Api.Example.Org",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert domains == ["www.example.com", "api.example.org"]

    def test_base_domain_from_adblock_syntax(self) -> None:
        """Test extracting base domain from AdBlock syntax.

        When a list has ||redgifs.com^, the output should be redgifs.com,
        which DNS blockers interpret as blocking all subdomains.
        """
        lines = iter(
            [
                "||redgifs.com^",
                "||pornhub.com^",
            ]
        )
        domains = list(extract_domains_from_lines(lines))

        assert "redgifs.com" in domains
        assert "pornhub.com" in domains

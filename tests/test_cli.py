"""Tests for YAHA-specific reporting rules."""

from src.cli import get_candidate_reasons


def test_low_contribution_threshold_is_inclusive() -> None:
    """A source contributing exactly 50 domains is a candidate."""
    reasons = get_candidate_reasons(50, None)

    assert reasons == ["50 unique domains"]


def test_contribution_above_threshold_is_not_a_candidate() -> None:
    """A source contributing more than 50 domains is not low-value."""
    assert get_candidate_reasons(51, None) == []


def test_stale_source_is_a_candidate() -> None:
    """The staleness reason includes the observed unchanged duration."""
    reasons = get_candidate_reasons(51, 30)

    assert reasons == ["unchanged 30 days"]


def test_source_can_have_both_candidate_reasons() -> None:
    """Low contribution and staleness are reported together."""
    reasons = get_candidate_reasons(1, 45)

    assert reasons == [
        "1 unique domain",
        "unchanged 45 days",
    ]

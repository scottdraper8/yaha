# Yaha Security Audit

**Date:** July 3, 2026  
**Status:** Remediated
**Scope:** Application code, dependency management, GitHub repository settings,
and GitHub Actions

## Remediation Outcome

All actionable findings in this audit were implemented and verified on July 3,
2026. The remediation was merged through protected pull requests and validated
on both local and GitHub-hosted runners.

Notable outcomes include:

- `curl-cffi` was upgraded from 0.14.0 to 0.15.0 after the new audit gate found
  CVE-2026-33752. The application-level redirect and private-address checks
  remain in place as defense in depth.
- The complete 94-test suite, Ruff, strict mypy, pre-commit, Gitleaks,
  `pip-audit`, `actionlint`, and CodeQL pass.
- A full local analysis completed against all 23 configured sources.
- Multiple production workflow dispatches verified the read-only analysis job,
  artifact boundary, write-isolated publisher, repeated PR lifecycle, and
  required CI integration.
- GitHub Actions are restricted to GitHub-owned Actions plus the explicitly
  allowed `astral-sh/setup-uv` and `step-security/harden-runner` publishers.
  Full commit SHA enforcement is enabled.
- `main` requires pull requests and the `Validate` check, enforces protection
  for administrators, and blocks force pushes and deletion.
- Dependabot alerts and security updates and CodeQL default setup are enabled.
  Routine dependency update PRs remain disabled.

GitHub left secret-scanning validity checks and non-provider patterns disabled
when enablement was requested; those account-level features are not available
for this repository. A public security policy and vulnerability intake channel
are intentionally omitted because Yaha is maintained primarily for personal
use.

## Executive Summary

Yaha has several useful baseline controls: GitHub secret scanning and push
protection are enabled, dependencies are resolved through `uv.lock`, CI uses
locked/frozen installs, TLS certificate verification is enabled for source
downloads, and analysis aborts when a source cannot be fetched.

At audit time, the largest risk was the scheduled analysis workflow. It
executed project code and processed untrusted remote content in a job with
repository write permission, then pushed directly to an unprotected `main`
branch. Yaha also lacked automated vulnerability updates, required CI checks,
response-size limits, and enforced commit-SHA pinning for GitHub Actions. These
gaps are now remediated as described above.

The recommended model combines the strongest relevant controls observed in
ClickEase and dbinfo:

- Require pull requests for `main`, with zero approvals if Yaha remains a
  single-maintainer project.
- Run required validation before merging.
- Use exact dependency versions, a hash-bearing lockfile, and frozen installs.
- Disable routine Dependabot version PRs while retaining security update PRs.
- Pin GitHub Actions and pre-commit hooks to immutable commit SHAs.
- Run analysis without write credentials and publish generated changes through
  a pull request.
- Constrain network access and untrusted blocklist input.

## Audit Baseline

### Enabled

- GitHub secret scanning.
- GitHub secret scanning push protection.
- Read-only default `GITHUB_TOKEN` permissions at repository level.
- Explicit workflow permissions rather than an implicit global write token.
- Reproducible Python resolution through `uv.lock`.
- `uv sync --locked` and `uv run --frozen` in automation.
- TLS certificate verification for source downloads.
- SHA-256 content hashing for change detection.
- Analysis fails closed when any configured source fetch fails.
- Subprocess execution uses an argument list rather than shell interpolation.
- Pre-commit checks detect private keys, malformed configuration files, merge
  conflicts, and oversized files.

### Audit-Time Gaps (Now Remediated)

- Branch protection or repository rulesets for `main`.
- Required pull requests and required CI status checks.
- Dependabot alerts and Dependabot security updates.
- Dependabot configuration for uv, GitHub Actions, and pre-commit.
- Code scanning.
- Restrictions on allowed GitHub Actions.
- Enforcement of full-length commit SHA pins for Actions.
- Network egress monitoring or filtering in the analysis workflow.

## Comparative Findings

### ClickEase

ClickEase demonstrates branch protection, restricted Actions, Gitleaks, and
Step Security Harden Runner in audit mode. However, it is not a complete model:
Dependabot and code scanning are disabled, and Actions are referenced by mutable
tags rather than full commit SHAs.

### dbinfo

dbinfo provides the more relevant dependency and merge-control model:

- Direct dependencies and the package-manager version are pinned exactly.
- Transitive dependencies are fixed by a lockfile.
- CI installs with a frozen lockfile and performs a vulnerability audit.
- Dependency build scripts are restricted to an explicit allowlist.
- GitHub Actions are pinned to full commit SHAs.
- Dependabot security updates are enabled.
- `open-pull-requests-limit: 0` suppresses routine version-update PRs while
  allowing security-update PRs.
- `main` requires pull requests with zero approving reviews and applies the
  rule to administrators.

Controls that should not be copied from dbinfo include its repository-wide
default write token and unrestricted Actions policy. Repository privacy reduces
exposure to untrusted contributors but does not eliminate registry, dependency,
Action, or self-hosted-runner supply-chain risks.

## Severity Criteria

| Level | Meaning |
| ------- | --------- |
| High | Exploitable without unusual preconditions, or failure directly compromises repository integrity, credentials, or availability. |
| Medium | Requires a specific precondition (e.g., a malicious PR merged, attacker-controlled configuration) or the impact is limited by an external control such as GitHub's Markdown sanitizer. |
| Low | Defense-in-depth improvement with no direct exploit path under current conditions. |

## Findings and Recommendations

### YAHA-01: Write-Enabled Analysis Job and Direct Push

**Severity:** High  
**Location:** `.github/workflows/analyze-host-lists.yml`

The analysis job receives `contents: write` before checkout, dependency setup,
installation, application execution, and network retrieval. Checkout persists
Git credentials by default. Compromised project code, an Action, or an installed
dependency could therefore use the workflow credential to modify the
repository. The workflow pushes generated files directly to an unprotected
`main` branch.

**Recommendations:**

1. Set top-level workflow permissions to `contents: read`.
2. Run analysis in a read-only job with `persist-credentials: false`.
3. Publish only `README.md` and `state.json` through a separate minimal job
   that receives files via workflow artifacts.
4. Prefer an automated pull request over a direct push.
5. Validate the generated file set and JSON structure before creating the PR.

### YAHA-02: Unprotected Default Branch

**Severity:** High

`main` has no classic branch protection and no ruleset. Changes can bypass
testing, and force pushes or branch deletion are not explicitly prohibited.

**Recommendations:**

- Require pull requests for `main`.
- Use zero required approvals if there is only one maintainer.
- Require the CI workflow to pass before merge.
- Dismiss stale approvals if approvals are later required.
- Block force pushes and deletion.
- Enforce the rule for administrators.
- Require conversation resolution.

### YAHA-03: Dependency Vulnerability Monitoring Disabled

**Severity:** High

Dependabot alerts, Dependabot security updates, and automated security fixes are
disabled. The lockfile makes current installs deterministic but does not notify
the maintainer when a locked version becomes vulnerable.

**Recommendations:**

1. Enable the dependency graph, Dependabot alerts, and Dependabot security
   updates in repository settings.
2. Add `.github/dependabot.yml`:

   ```yaml
   version: 2
   updates:
     - package-ecosystem: "uv"
       directory: "/"
       schedule:
         interval: "weekly"
       open-pull-requests-limit: 0

     - package-ecosystem: "github-actions"
       directory: "/"
       schedule:
         interval: "weekly"
       open-pull-requests-limit: 0

     - package-ecosystem: "pre-commit"
       directory: "/"
       schedule:
         interval: "weekly"
       open-pull-requests-limit: 0
   ```

3. Run the exactly pinned `pip-audit` audit dependency against a hash-preserving
   export of `uv.lock` in required CI.

The zero PR limit disables routine version-update PRs. Dependabot security
updates use a separate internal PR limit.

### YAHA-04: Dependency Constraints Permit Unreviewed Resolution Changes

**Severity:** Medium

`pyproject.toml` specifies compatible ranges while `uv.lock` fixes the installed
versions. Current CI remains deterministic because it uses the lockfile, but a
lockfile regeneration or installation without the lockfile may select a newer,
unreviewed release.

Because Yaha is an application rather than a reusable library, exact direct
pins are appropriate. Pin manifest dependencies to the reviewed lockfile
versions and update both manifest and lockfile through reviewed security PRs.
Artifact hashes in `uv.lock` and frozen installs remain the primary enforcement
controls.

### YAHA-05: Mutable GitHub Action and Hook References

**Severity:** High

The workflow references `actions/checkout@v5` and
`astral-sh/setup-uv@v8.2.0`. Pre-commit hooks also use tags. Tags can move; an
exact-looking tag is not an immutable reference.

**Recommendations:**

- Pin every Action and pre-commit repository to a full commit SHA.
- Add a comment containing the human-readable release next to each SHA.
- Restrict repository Actions to GitHub-owned, verified, and explicitly allowed
  publishers.
- Enable repository enforcement of full-length SHA pins after converting the
  workflow.

### YAHA-06: No Required CI Gate

**Severity:** High

The existing workflow performs production analysis but does not run the test,
lint, formatting, or type-checking suites before executing changed code.

Add a separate pull-request workflow that runs:

```text
uv sync --locked
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest
uv run --group audit pip-audit <hash-locked requirements export>
```

Keep `pip-audit` in a dedicated dependency group so the scanner and its
transitive dependencies are versioned and hashed in `uv.lock` rather than
resolved dynamically by `uvx`.

Make this workflow a required status check for `main`.

### YAHA-07: Unbounded Remote Responses

**Severity:** High  
**Location:** `src/fetcher.py`

Each remote response is loaded and decoded entirely in memory. There is no
maximum compressed size, decoded size, line length, domain count, or aggregate
download budget. A compromised or malfunctioning source can exhaust runner
memory or disk. Five concurrent fetch workers each hold a full decoded
response body plus a UTF-8 re-encoding for hashing, so peak resident memory
can reach roughly ten times the size of a single source response.

**Recommendations:**

- Stream each response to a private temporary file while hashing raw bytes.
- Enforce per-source and aggregate byte limits calibrated against current
  source sizes.
- Enforce a maximum line length and domain count.
- Use separate connection and read timeouts.
- Retry only transient transport failures and selected server status codes.
- Reject unexpected content encodings where practical.
- Clean up partial files on every failure path.

### YAHA-08: URL and Redirect Validation

**Severity:** Medium  
**Location:** `src/config.py`, `src/fetcher.py`

Source configuration requires a name and URL but does not validate URL scheme,
host, credentials, fragments, duplicates, or redirect destinations. This
increases SSRF and configuration-confusion exposure if a malicious source entry
is merged.

**Recommendations:**

- Accept HTTPS URLs only.
- Reject embedded credentials and nonstandard schemes.
- Require unique source names and URLs.
- Reject loopback, link-local, private, and metadata-service destinations,
  including redirect targets.
- Consider an explicit hostname allowlist for the small set of trusted source
  providers.
- Add Harden Runner in egress audit mode, then evaluate a blocking policy.

### YAHA-09: Predictable Temporary Files

**Severity:** Medium  
**Location:** `src/pipeline.py`

The pipeline writes fixed filenames in the current directory. Existing symlinks
or concurrent executions can cause file clobbering, corruption, or unintended
file replacement. The workflow `concurrency` group prevents parallel CI runs,
which limits this risk in production, but local development and direct CLI
invocations remain vulnerable.

Use `tempfile.TemporaryDirectory` or securely created named temporary files,
restrict permissions, and guarantee cleanup with context managers.

### YAHA-10: Generated Markdown Does Not Escape Configuration

**Severity:** Medium  
**Location:** `src/cli.py`

Source names, source URLs, maintainer names, descriptions, and maintainer URLs
are interpolated into generated HTML or Markdown without escaping. Source URLs
appear inside single-quoted `href` attributes; a URL containing a single
quote can break out of the attribute. GitHub sanitizes rendered content, but
malformed or hostile configuration can still inject links or alter document
structure when the output is consumed outside GitHub.

Validate URLs and escape all configuration-derived HTML and Markdown values
before rendering.

### YAHA-11: Broad Exception Handling in Fetch Retry Loop

**Severity:** Low
**Location:** `src/fetcher.py`

The retry loop catches bare `Exception`, which retries on programming errors
(`TypeError`, `AttributeError`, `UnicodeDecodeError`) the same way it retries
transport failures. A malformed response that triggers a decoding error is
retried silently three times instead of surfacing the root cause.

**Recommendation:**

Catch `curl_cffi.requests.RequestsError` (and its subclass `HTTPError`)
rather than `Exception`. Let unexpected errors propagate immediately.

### YAHA-12: Secret-Scanning Hygiene

**Severity:** Low

GitHub secret scanning and push protection are enabled, but local hooks only
detect private-key patterns.

**Recommendations:**

- Add Gitleaks to pre-commit and CI.
- Enable secret validity checks and non-provider patterns if available for the
  repository.

A public security policy and vulnerability intake channel are intentionally
omitted because this repository is maintained primarily for personal use.

## Recommended Implementation Order

1. Add required CI and dependency auditing.
2. Convert the scheduled update to a pull-request workflow with read-only
   analysis permissions.
3. Protect `main` using the dbinfo-style zero-approval PR model.
4. Enable Dependabot alerts and security updates, then add the security-only
   Dependabot configuration.
5. Pin dependencies, Actions, and hooks to immutable versions or SHAs.
6. Restrict allowed Actions and add Harden Runner egress auditing.
7. Add response-size limits, streaming downloads, and URL validation.
8. Replace predictable temporary files and escape generated output.
9. Narrow the fetch retry exception type.
10. Add Gitleaks and enable additional secret-scanning checks where available.

## Verification Checklist

- [x] Pull requests cannot merge until tests, linting, typing, and audits pass.
- [x] Direct pushes, force pushes, and deletion of `main` are blocked.
- [x] Scheduled analysis cannot access a repository write token.
- [x] Generated updates arrive as reviewable pull requests.
- [x] Dependabot creates vulnerability PRs but not routine update PRs.
- [x] All Actions are full-SHA pinned and repository enforcement is enabled.
- [x] All dependency installs use the committed lockfile without re-resolution.
- [x] Remote downloads have tested size, time, redirect, and destination limits.
- [x] Concurrent runs cannot share or overwrite temporary files.
- [x] Gitleaks and GitHub secret scanning protect both local and remote changes.

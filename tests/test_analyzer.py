"""
test_analyzer.py — Accuracy test suite for RootCauseAnalyzer.
M2 owns this file.

10 labeled test cases: 2 per failure category.
Run before the demo to confirm >80% accuracy.

Usage:
    python -m pytest tests/test_analyzer.py -v
    python -m pytest tests/test_analyzer.py -v --tb=short   # concise output

Each test checks:
  1. category matches expected label
  2. confidence is above the minimum threshold for the path taken
"""

import pytest
from unittest.mock import patch, MagicMock
from autoheal.analyzer.analyzer import RootCauseAnalyzer, RootCauseResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def analyzer():
    """Fresh analyzer instance for each test — dedup cache is empty."""
    return RootCauseAnalyzer()


def _make_stats(mem_pct: float = 0.5) -> dict:
    """Helper: build a minimal Docker stats dict at the given memory %."""
    limit = 512 * 1024 * 1024  # 512 MB
    return {
        "memory_stats": {
            "usage": int(limit * mem_pct),
            "limit": limit,
        }
    }


# ---------------------------------------------------------------------------
# OOM — 2 cases
# ---------------------------------------------------------------------------

class TestOOM:

    def test_oom_kernel_kill(self, analyzer):
        """Kernel OOM killer fires — most unambiguous signal."""
        logs = (
            "2024-01-15T02:14:33Z [kernel] Out of memory: Kill process 1842 (python) "
            "score 892 or sacrifice child\n"
            "2024-01-15T02:14:33Z [kernel] OOMKilled process 1842\n"
            "2024-01-15T02:14:33Z Container exited with code 137"
        )
        result = analyzer.analyze("payments-api", logs, _make_stats(0.98), "process_crash")

        assert result.category == "OOM", f"Expected OOM, got {result.category}"
        assert result.confidence >= 0.90, f"Expected high confidence, got {result.confidence}"

    def test_oom_memory_exhaustion_log(self, analyzer):
        """App-level memory exhaustion before kernel kill."""
        logs = (
            "Allocating chunk 1024MB...\n"
            "Allocating chunk 2048MB...\n"
            "fatal error: runtime: out of memory\n"
            "goroutine 1 [running]: runtime.throw(0x...)\n"
            "Killed process due to memory limit exceeded"
        )
        result = analyzer.analyze("worker", logs, _make_stats(0.99), "oom_risk")

        assert result.category == "OOM", f"Expected OOM, got {result.category}"
        assert result.confidence >= 0.85


# ---------------------------------------------------------------------------
# Application crash — 2 cases
# ---------------------------------------------------------------------------

class TestApplicationCrash:

    def test_crash_python_exception(self, analyzer):
        """Unhandled Python exception with full traceback."""
        logs = (
            "INFO  Starting payment processor\n"
            "INFO  Connected to database\n"
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 142, in process_payment\n"
            "    result = payment_gateway.charge(amount)\n"
            "RuntimeError: Payment gateway returned unexpected status 500\n"
            "Process exited with code 1"
        )
        result = analyzer.analyze("payments-api", logs, _make_stats(0.3), "process_crash")

        assert result.category == "application_crash", (
            f"Expected application_crash, got {result.category}"
        )
        assert result.confidence >= 0.75

    def test_crash_segfault(self, analyzer):
        """Native segfault — C extension or system-level crash."""
        logs = (
            "Starting worker process pid=4201\n"
            "Processing job queue...\n"
            "Segmentation fault (core dumped)\n"
            "signal 11 (SIGSEGV), address 0x0000000000000008"
        )
        result = analyzer.analyze("worker", logs, _make_stats(0.4), "process_crash")

        assert result.category == "application_crash", (
            f"Expected application_crash, got {result.category}"
        )
        assert result.confidence >= 0.90


# ---------------------------------------------------------------------------
# Dependency failure — 2 cases
# ---------------------------------------------------------------------------

class TestDependencyFailure:

    def test_dep_connection_refused(self, analyzer):
        """Cannot reach downstream service — TCP connection refused."""
        logs = (
            "INFO  auth-service starting on :5002\n"
            "INFO  Attempting database connection...\n"
            "ERROR dial tcp 10.0.0.5:5432: connect: connection refused\n"
            "ERROR ECONNREFUSED connecting to postgres://db:5432/authdb\n"
            "FATAL Cannot start without database connection, exiting"
        )
        result = analyzer.analyze("auth-service", logs, _make_stats(0.2), "process_crash")

        assert result.category == "dependency_failure", (
            f"Expected dependency_failure, got {result.category}"
        )
        assert result.confidence >= 0.85

    def test_dep_dns_resolution_failure(self, analyzer):
        """DNS lookup failure — service name not resolvable."""
        logs = (
            "Connecting to redis-cluster.internal:6379...\n"
            "getaddrinfo redis-cluster.internal failed: Name or service not known\n"
            "ConnectionError: Failed to connect to Redis after 3 retries\n"
            "Worker cannot proceed without cache layer"
        )
        result = analyzer.analyze("worker", logs, _make_stats(0.1), "unresponsive")

        assert result.category == "dependency_failure", (
            f"Expected dependency_failure, got {result.category}"
        )
        assert result.confidence >= 0.80


# ---------------------------------------------------------------------------
# Config error — 2 cases
# ---------------------------------------------------------------------------

class TestConfigError:

    def test_config_missing_env_var(self, analyzer):
        """Required environment variable not set."""
        logs = (
            "Loading configuration...\n"
            "KeyError: 'DATABASE_URL'\n"
            "Traceback (most recent call last):\n"
            "  File 'config.py', line 18, in load\n"
            "    db_url = os.environ['DATABASE_URL']\n"
            "KeyError: 'DATABASE_URL'\n"
            "Configuration error: required env var DATABASE_URL not set"
        )
        result = analyzer.analyze("db-client", logs, _make_stats(0.05), "process_crash")

        assert result.category == "config_error", (
            f"Expected config_error, got {result.category}"
        )
        assert result.confidence >= 0.80

    def test_config_missing_module(self, analyzer):
        """Python import error — dependency not installed in image."""
        logs = (
            "Python 3.11.4\n"
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 3, in <module>\n"
            "    import prometheus_client\n"
            "ModuleNotFoundError: No module named 'prometheus_client'\n"
            "Hint: run 'pip install prometheus-client' or check requirements.txt"
        )
        result = analyzer.analyze("payments-api", logs, _make_stats(0.05), "process_crash")

        assert result.category == "config_error", (
            f"Expected config_error, got {result.category}"
        )
        assert result.confidence >= 0.85


# ---------------------------------------------------------------------------
# Unknown — 2 cases (ambiguous signals, Claude path)
# These use mocking to avoid real API calls in CI.
# ---------------------------------------------------------------------------

class TestUnknown:

    @patch("autoheal.analyzer.analyzer.anthropic.Anthropic")
    def test_unknown_ambiguous_logs(self, mock_anthropic_cls, analyzer):
        """
        Logs are noisy but don't match any fast-path pattern.
        Expect Claude to be called and return 'unknown' with low confidence.
        """
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"category":"unknown","confidence":0.45,'
                                                '"summary":"Cannot determine root cause from available signals",'
                                                '"key_signals":[],'
                                                '"recommended_action":"Attach debugger and check system metrics"}')]
        mock_client.messages.create.return_value = mock_response

        # Re-create analyzer so it uses the mocked Anthropic client
        fresh_analyzer = RootCauseAnalyzer()
        fresh_analyzer.client = mock_client

        logs = (
            "INFO  Processing request batch 4419\n"
            "INFO  Batch completed in 342ms\n"
            "WARN  Slow response from internal cache (820ms)\n"
            "INFO  Processing request batch 4420\n"
            "Container stopped unexpectedly"
        )
        result = fresh_analyzer.analyze("nginx", logs, _make_stats(0.45), "unresponsive")

        # Unknown with low confidence is the correct answer here
        assert result.category == "unknown"
        assert result.confidence < 0.70

    @patch("autoheal.analyzer.analyzer.anthropic.Anthropic")
    def test_unknown_empty_logs(self, mock_anthropic_cls, analyzer):
        """
        Container died with no logs at all — very common with OOMKill before logging.
        Fast-path misses (empty string). Claude path is called.
        """
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"category":"unknown","confidence":0.30,'
                                                '"summary":"No logs available — container may have been killed before logging",'
                                                '"key_signals":[],'
                                                '"recommended_action":"Check host-level dmesg for OOM events"}')]
        mock_client.messages.create.return_value = mock_response

        fresh_analyzer = RootCauseAnalyzer()
        fresh_analyzer.client = mock_client

        result = fresh_analyzer.analyze("worker", "", _make_stats(0.0), "not_found")

        assert result.category == "unknown"
        assert result.confidence < 0.50


# ---------------------------------------------------------------------------
# Dedup guard
# ---------------------------------------------------------------------------

class TestDedupGuard:

    @patch("autoheal.analyzer.analyzer.anthropic.Anthropic")
    def test_dedup_prevents_second_claude_call(self, mock_anthropic_cls):
        """
        Calling analyze() twice rapidly on the same container should only
        fire one Claude API call. Second call hits the dedup guard.
        """
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"category":"application_crash","confidence":0.80,'
                                                '"summary":"App crashed",'
                                                '"key_signals":["crash"],'
                                                '"recommended_action":"Check logs"}')]
        mock_client.messages.create.return_value = mock_response

        analyzer = RootCauseAnalyzer()
        analyzer.client = mock_client

        # Both calls have ambiguous logs (skip fast-path)
        ambiguous_logs = "Container stopped unexpectedly with exit code 1"

        # First call — should hit Claude
        analyzer.analyze("payments-api", ambiguous_logs, _make_stats(), "process_crash")
        # Second call immediately after — dedup guard should block Claude
        result = analyzer.analyze("payments-api", ambiguous_logs, _make_stats(), "process_crash")

        # Claude should only have been called once
        assert mock_client.messages.create.call_count == 1
        # Second result should be an 'unknown' from the dedup guard
        assert result.category == "unknown"


# ---------------------------------------------------------------------------
# Accuracy summary helper (run manually for demo prep)
# ---------------------------------------------------------------------------

def run_accuracy_report():
    """
    Run all fast-path test cases and print an accuracy table.
    Use this before the demo to confirm >80% accuracy.

    Run with:  python -c "from tests.test_analyzer import run_accuracy_report; run_accuracy_report()"
    """
    analyzer = RootCauseAnalyzer()

    cases = [
        # (label, container, logs, stats, failure_type)
        ("OOM",                 "payments-api", "OOMKilled process 1842",                    _make_stats(0.98), "process_crash"),
        ("OOM",                 "worker",       "fatal error: runtime: out of memory",       _make_stats(0.99), "oom_risk"),
        ("application_crash",   "payments-api", "Traceback (most recent call last):\nRuntimeError: Payment gateway error", _make_stats(0.3), "process_crash"),
        ("application_crash",   "worker",       "Segmentation fault (core dumped)",          _make_stats(0.4), "process_crash"),
        ("dependency_failure",  "auth-service", "ECONNREFUSED connecting to postgres://db",  _make_stats(0.2), "process_crash"),
        ("dependency_failure",  "worker",       "getaddrinfo redis.internal failed: Name or service not known", _make_stats(0.1), "unresponsive"),
        ("config_error",        "db-client",    "KeyError: 'DATABASE_URL'",                  _make_stats(0.05), "process_crash"),
        ("config_error",        "payments-api", "ModuleNotFoundError: No module named 'prometheus_client'", _make_stats(0.05), "process_crash"),
    ]

    correct = 0
    print(f"\n{'Container':<16} {'Expected':<22} {'Got':<22} {'Conf':>6}  {'Pass'}")
    print("-" * 80)
    for expected_cat, container, logs, stats, failure_type in cases:
        result = analyzer.analyze(container, logs, stats, failure_type)
        passed = result.category == expected_cat
        if passed:
            correct += 1
        mark = "✓" if passed else "✗"
        print(f"{container:<16} {expected_cat:<22} {result.category:<22} {result.confidence:>5.0%}  {mark}")

    total = len(cases)
    accuracy = correct / total * 100
    print(f"\nAccuracy: {correct}/{total} = {accuracy:.0f}%  (target: ≥80%)")
    if accuracy >= 80:
        print("✓ PASS — Ready for demo")
    else:
        print("✗ FAIL — Review failing cases before demo")


if __name__ == "__main__":
    run_accuracy_report()

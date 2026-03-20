"""
tests/test_monitor.py
Unit tests for the monitor, analyzer, and healer modules.
Run with: pytest tests/
"""
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from autoheal.monitor.monitor import detect_issues
from autoheal.analyzer.analyzer import analyze_incident
from autoheal.schemas.incident import IssueType


# ---------------------------------------------------------------------------
# monitor
# ---------------------------------------------------------------------------

class TestDetectIssues:
    def _mock_run(self, stdout: str):
        mock = MagicMock()
        mock.stdout = stdout
        mock.returncode = 0
        return mock

    def test_returns_exited_containers(self):
        exited_line = '{"Names":"payments-api","Status":"Exited (1) 2 minutes ago","Health":""}'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                self._mock_run(exited_line),  # exited/dead query
                self._mock_run(""),           # unhealthy query
            ]
            result = detect_issues()
        assert len(result) == 1
        assert result[0]["Names"] == "payments-api"

    def test_returns_unhealthy_containers(self):
        unhealthy_line = '{"Names":"worker","Status":"Up 5 minutes","Health":"unhealthy"}'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                self._mock_run(""),            # exited/dead query
                self._mock_run(unhealthy_line) # unhealthy query
            ]
            result = detect_issues()
        assert len(result) == 1
        assert result[0]["Names"] == "worker"

    def test_empty_when_all_healthy(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._mock_run("")
            result = detect_issues()
        assert result == []


# ---------------------------------------------------------------------------
# analyzer
# ---------------------------------------------------------------------------

class TestAnalyzeIncident:
    @pytest.mark.parametrize("status,health,expected", [
        ("Exited (1) 3 minutes ago", "",           IssueType.crashed),
        ("Exited (0) 1 hour ago",    "",           IssueType.stopped),
        ("Dead",                     "",           IssueType.dead),
        ("Up 2 hours",               "unhealthy",  IssueType.unhealthy),
        ("Up 2 hours",               "",           IssueType.unknown),
    ])
    def test_classify(self, status, health, expected):
        container = {"Status": status, "Health": health}
        result = analyze_incident(container)
        assert IssueType(result) == expected


# ---------------------------------------------------------------------------
# healer
# ---------------------------------------------------------------------------

class TestHeal:
    def test_returns_true_on_success(self):
        from autoheal.healer.healer import heal
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            assert heal("payments-api") is True

    def test_returns_false_on_failure(self):
        from autoheal.healer.healer import heal
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "no such container"
        with patch("subprocess.run", return_value=mock_result):
            assert heal("ghost-container") is False

"""
analyzer.py — Root-cause analysis engine for Auto-Heal.
M2 owns this file.

Flow:
  1. Fast-path: regex patterns catch 85%+ of obvious failures instantly.
  2. Slow-path: Claude API (Sonnet) for ambiguous / multi-signal cases.
  3. Dedup guard: one Claude call per container per 60s to prevent API spam.
"""

import re
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data contract — M1's healer.py imports RootCauseResult. Do NOT rename fields.
# ---------------------------------------------------------------------------

@dataclass
class RootCauseResult:
    category: str           # OOM | application_crash | dependency_failure | config_error | unknown
    confidence: float       # 0.0 – 1.0
    summary: str            # one-sentence human-readable explanation
    key_signals: list       # list of strings — log snippets / stat signals
    recommended_action: str # what a human should do if auto-heal fails


# ---------------------------------------------------------------------------
# Fast-path regex patterns (ordered most-specific → least-specific)
# Covers ~85% of real failures without burning Claude API tokens.
# ---------------------------------------------------------------------------

FAST_PATTERNS: list[tuple[str, str, float]] = [
    # OOM — kernel-level kill signals
    (r"OOMKilled|Killed process.*memory|out of memory kill|oom.kill",
     "OOM", 0.98),

    # Dependency failures — network / connection refused
    (r"ConnectionRefused|ECONNREFUSED|dial tcp|connection refused|no route to host|"
     r"Name or service not known|getaddrinfo.*failed",
     "dependency_failure", 0.92),

    # Config / import errors — missing modules, bad env vars
    (r"Cannot find module|ImportError|ModuleNotFoundError|"
     r"KeyError.*environ|No such file or directory.*config|"
     r"invalid value for|configuration error",
     "config_error", 0.91),

    # Permission errors — also config-class
    (r"permission denied|EACCES|EPERM|Operation not permitted",
     "config_error", 0.86),

    # Hard crashes — segfaults, panics
    (r"Segmentation fault|SIGSEGV|core dumped|signal 11",
     "application_crash", 0.95),

    # Panics and fatal errors (Go, Python, Node)
    (r"panic:|fatal error:|FATAL|Traceback.*(?:Exception|Error)|"
     r"Unhandled exception|uncaughtException",
     "application_crash", 0.83),
]


# ---------------------------------------------------------------------------
# Claude system prompt — JSON-only response, strict schema
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert DevOps engineer analyzing container failures.
Your job is to classify the root cause based on container logs and runtime stats.

Respond ONLY with valid JSON — no preamble, no markdown fences, no extra keys:
{
  "category": "OOM|application_crash|dependency_failure|config_error|unknown",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence explanation of the failure>",
  "key_signals": ["<signal1>", "<signal2>"],
  "recommended_action": "<what a human should do if auto-heal fails>"
}

Category definitions:
- OOM: process killed due to memory exhaustion (OOMKilled, memory limit exceeded)
- application_crash: bug, exception, panic, segfault, or unhandled error in the app code
- dependency_failure: downstream service unavailable (DB, cache, API, DNS failures)
- config_error: missing env var, bad config file, wrong permissions, missing module
- unknown: cannot determine from the available signals

Rules:
- confidence >= 0.90 only when the signal is unambiguous
- confidence 0.70-0.89 for moderate evidence
- confidence < 0.70 for weak or conflicting signals
- key_signals must be short substrings actually present in the logs (max 60 chars each)
- recommended_action must be actionable (not "investigate further")"""


# ---------------------------------------------------------------------------
# Analyzer class
# ---------------------------------------------------------------------------

class RootCauseAnalyzer:
    """
    Analyzes container failure events and returns a structured RootCauseResult.

    Usage (from healer.py):
        analyzer = RootCauseAnalyzer()
        result = analyzer.analyze(container_name, logs, stats, failure_type)
    """

    def __init__(self):
        self.client = anthropic.Anthropic()
        # Dedup cache: container_id -> last_called_timestamp
        # Prevents spamming Claude when a container flaps repeatedly
        self._last_called: dict[str, float] = {}
        self._DEDUP_TTL = 60  # seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        container_name: str,
        logs: str,
        stats: dict,
        failure_type: str,
    ) -> RootCauseResult:
        """
        Analyze a container failure. Tries fast-path regex first,
        falls back to Claude API for ambiguous cases.

        Args:
            container_name: Docker container name or ID
            logs:           Last N lines of container logs (string)
            stats:          Docker stats dict (memory_stats, cpu_stats etc.)
            failure_type:   Pre-classification from monitor (process_crash, oom_risk, unresponsive…)

        Returns:
            RootCauseResult dataclass
        """
        logs = logs or ""

        # 1. Fast-path: regex
        fast = self._fast_path(logs)
        if fast:
            logger.info(
                "Fast-path hit for %s: %s (%.0f%%)",
                container_name, fast.category, fast.confidence * 100,
            )
            return fast

        # 2. Slow-path: Claude API (with dedup guard)
        if self._is_rate_limited(container_name):
            logger.warning(
                "Dedup guard: skipping Claude call for %s (called within last %ds)",
                container_name, self._DEDUP_TTL,
            )
            return self._unknown_result("Dedup guard active — too many events from this container")

        return self._claude_analyze(container_name, logs, stats, failure_type)

    # ------------------------------------------------------------------
    # Fast-path
    # ------------------------------------------------------------------

    def _fast_path(self, logs: str) -> Optional[RootCauseResult]:
        """Check logs against compiled regex patterns. Returns first match or None."""
        for pattern, category, confidence in FAST_PATTERNS:
            match = re.search(pattern, logs, re.IGNORECASE)
            if match:
                matched_text = match.group(0)[:60]
                return RootCauseResult(
                    category=category,
                    confidence=confidence,
                    summary=f"Pattern match: '{matched_text}'",
                    key_signals=[matched_text],
                    recommended_action=self._default_action(category),
                )
        return None

    # ------------------------------------------------------------------
    # Slow-path: Claude API
    # ------------------------------------------------------------------

    def _claude_analyze(
        self,
        container_name: str,
        logs: str,
        stats: dict,
        failure_type: str,
    ) -> RootCauseResult:
        """Call Claude API and parse structured JSON response."""
        self._last_called[container_name] = time.time()

        # Build memory % string for context
        mem_stats = stats.get("memory_stats", {})
        mem_usage = mem_stats.get("usage", 0)
        mem_limit = mem_stats.get("limit", 1) or 1
        mem_pct = mem_usage / mem_limit

        # Truncate logs to last 3000 chars to stay within token budget
        truncated_logs = logs[-3000:] if len(logs) > 3000 else logs

        prompt = (
            f"Container: {container_name}\n"
            f"Pre-classified failure type: {failure_type}\n"
            f"Memory usage: {mem_pct:.1%} of limit\n\n"
            f"Last log lines:\n{truncated_logs}"
        )

        try:
            logger.info("Calling Claude API for container: %s", container_name)
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            data = json.loads(raw)
            return RootCauseResult(
                category=data["category"],
                confidence=float(data["confidence"]),
                summary=data["summary"],
                key_signals=data.get("key_signals", []),
                recommended_action=data.get("recommended_action", "Manual investigation required"),
            )

        except json.JSONDecodeError as e:
            logger.error("Claude returned invalid JSON: %s", e)
            return self._unknown_result(f"Claude response parse error: {e}")

        except anthropic.APIError as e:
            logger.error("Claude API error: %s", e)
            return self._unknown_result(f"Claude API unavailable: {e}")

        except Exception as e:
            logger.error("Unexpected analyzer error: %s", e)
            return self._unknown_result(str(e))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_rate_limited(self, container_name: str) -> bool:
        last = self._last_called.get(container_name, 0)
        return (time.time() - last) < self._DEDUP_TTL

    def _unknown_result(self, reason: str) -> RootCauseResult:
        return RootCauseResult(
            category="unknown",
            confidence=0.0,
            summary=reason,
            key_signals=[],
            recommended_action="Manual investigation required — automated analysis failed",
        )

    @staticmethod
    def _default_action(category: str) -> str:
        actions = {
            "OOM":                 "Increase container memory limit or investigate memory leak",
            "application_crash":   "Check application logs for stack trace; review recent deploys",
            "dependency_failure":  "Verify downstream service health; check network/DNS config",
            "config_error":        "Review environment variables, secrets, and volume mounts",
            "unknown":             "Manual investigation required",
        }
        return actions.get(category, "Manual investigation required")

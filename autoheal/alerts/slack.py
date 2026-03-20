import httpx
import logging
from datetime import datetime, timezone

from autoheal.config.settings import settings

# ─── LOGGER ──────────────────────────────────────────────────────────────────
# Logs go to the same stdout stream as the rest of autoheal.
# You'll see these in `docker compose logs autoheal`
logger = logging.getLogger(__name__)


# ─── COLOUR CODES ────────────────────────────────────────────────────────────
# Slack attachments support a "color" sidebar. We use this to make
# the message instantly readable at a glance in the Slack channel.
_COLORS = {
    "critical": "#ef4444",   # red   — service is down
    "high":     "#f59e0b",   # amber — degraded / warning
    "healing":  "#38bdf8",   # blue  — healer is working on it
    "resolved": "#22c55e",   # green — back to healthy
}

# ─── EMOJI MAP ───────────────────────────────────────────────────────────────
_EMOJI = {
    "critical": ":red_circle:",
    "high":     ":warning:",
    "healing":  ":arrows_counterclockwise:",
    "resolved": ":white_check_mark:",
}


# ─── MAIN FUNCTION ───────────────────────────────────────────────────────────
async def send_slack_alert(
    service:    str,
    event_type: str,          # "critical" | "high" | "healing" | "resolved"
    message:    str,
    root_cause: str  = "",
    action:     str  = "",
    heal_time:  int  = None,  # seconds, only on resolved events
) -> bool:
    """
    Sends a formatted Slack message via the incoming webhook URL
    configured in settings (SLACK_WEBHOOK_URL env var).

    Returns True if the message was sent successfully, False otherwise.

    Called by healer.py (M1) at two moments:
      1. When an incident is detected   → event_type="critical" or "high"
      2. When a service recovers        → event_type="resolved"
      3. While healing is in progress   → event_type="healing"

    Example Slack message for a critical alert:
      🔴 payments-api is DOWN
      Root cause: OOM kill — memory leak in /checkout handler
      Action: Pulling fresh image and restarting container
      2024-01-15 14:31:07 UTC
    """

    # ── Guard: if no webhook URL is configured, skip silently ────────────────
    # During local dev you might not have Slack set up yet — that's fine.
    if not settings.SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping Slack alert")
        return False

    # ── Build the timestamp string ────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── Build the message text ────────────────────────────────────────────────
    emoji  = _EMOJI.get(event_type, ":bell:")
    color  = _COLORS.get(event_type, "#888888")

    # Title line — e.g. "🔴 payments-api is DOWN"
    titles = {
        "critical": f"{emoji} *{service}* is DOWN",
        "high":     f"{emoji} *{service}* is DEGRADED",
        "healing":  f"{emoji} Healing *{service}*...",
        "resolved": f"{emoji} *{service}* recovered",
    }
    title = titles.get(event_type, f"{emoji} *{service}* — {event_type}")

    # Build the body fields
    fields = []

    if message:
        fields.append({"title": "What happened", "value": message, "short": False})

    if root_cause:
        fields.append({"title": "Root cause", "value": root_cause, "short": False})

    if action:
        fields.append({"title": "Action taken", "value": action, "short": True})

    if heal_time is not None:
        fields.append({"title": "Heal time", "value": f"{heal_time}s", "short": True})

    # ── Slack payload using "attachments" format ──────────────────────────────
    # This gives us the coloured sidebar and structured fields.
    payload = {
        "attachments": [
            {
                "color":      color,
                "title":      title,
                "fields":     fields,
                "footer":     f"autoheal · {ts}",
                "footer_icon": "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f527.png",
            }
        ]
    }

    # ── Send the HTTP POST to the Slack webhook ───────────────────────────────
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                settings.SLACK_WEBHOOK_URL,
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
            logger.info(f"Slack alert sent: [{event_type}] {service}")
            return True

    except httpx.TimeoutException:
        logger.error(f"Slack alert timed out for {service}")
        return False

    except httpx.HTTPStatusError as e:
        logger.error(f"Slack webhook rejected message: {e.response.status_code} — {e.response.text}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error sending Slack alert: {e}")
        return False

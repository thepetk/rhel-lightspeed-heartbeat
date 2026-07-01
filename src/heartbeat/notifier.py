import logging
from typing import Any

import httpx

from heartbeat.models import AlertPayload, AlertState, HealthResult, HealthStatus

logger = logging.getLogger(__name__)

_STATUS_EMOJI = {
    HealthStatus.HEALTHY: ":white_check_mark:",
    HealthStatus.UNHEALTHY: ":x:",
    HealthStatus.DEGRADED: ":warning:",
    HealthStatus.TIMEOUT: ":hourglass:",
    HealthStatus.ERROR: ":x:",
}


class SlackNotifier:
    def __init__(self, webhook_url: "str", client: "httpx.AsyncClient | None" = None) -> None:
        self._webhook_url = webhook_url
        self._client = client
        self._owns_client = client is None

    async def send(self, payload: "AlertPayload") -> "bool":
        """
        sends a notification to the Slack webhook with the given alert payload.
        """
        client = self._client or httpx.AsyncClient()
        try:
            message = _build_message(payload)
            response = await client.post(self._webhook_url, json=message)
            if response.status_code != 200 or response.text != "ok":
                logger.error("Slack notification failed: %s %s", response.status_code, response.text)
                return False
            return True
        except httpx.HTTPError as e:
            logger.error("Slack notification network error: %s", e)
            return False
        finally:
            if self._owns_client:
                await client.aclose()


def _build_message(payload: "AlertPayload") -> "dict[str, Any]":
    """
    builds a Slack message payload from the given alert payload, including the
    alert state, summary, and details of each service result.
    """
    is_firing = payload.state == AlertState.FIRING
    color = "#EE0000" if is_firing else "#36A64F"
    firing_count = sum(1 for r in payload.results if not r.is_healthy)

    if is_firing:
        header = f":rotating_light: [FIRING:{firing_count}] Heartbeat"
    else:
        header = ":white_check_mark: [RESOLVED] Heartbeat"

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*Alert:*\nServiceDown"},
                {"type": "mrkdwn", "text": f"*Summary:*\n{payload.summary}"},
            ],
        },
        {"type": "divider"},
    ]

    for result in payload.results:
        blocks.extend(_build_service_blocks(result))

    blocks.append({"type": "divider"})
    blocks.append(_build_footer(payload))

    return {"attachments": [{"color": color, "blocks": blocks}]}


def _build_service_blocks(result: "HealthResult") -> "list[dict[str, Any]]":
    """
    builds Slack message blocks for a single service health result, including the
    service name, status, response time, and any error messages.
    """
    emoji = _STATUS_EMOJI.get(result.status, ":question:")
    status_text = f"{emoji} {result.status.value.upper()}"
    if result.status_code is not None:
        status_text += f" (HTTP {result.status_code})"

    fields: list[dict[str, Any]] = [
        {"type": "mrkdwn", "text": f"*Service:*\n{result.service.name}"},
        {"type": "mrkdwn", "text": f"*Status:*\n{status_text}"},
    ]

    context_parts = []
    if result.response_time_ms is not None:
        context_parts.append(f"Response time: {result.response_time_ms:.0f}ms")
        if result.service.response_time_threshold_ms is not None:
            context_parts.append(f"Threshold: {result.service.response_time_threshold_ms:.0f}ms")
    if result.error_message:
        context_parts.append(f"Error: {result.error_message}")
    if result.service.auth is not None:
        context_parts.append(f"Auth: {result.service.auth.type}")
    context_parts.append(f"URL: {result.service.url}{result.service.health_path}")

    return [
        {"type": "section", "fields": fields},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": " | ".join(context_parts)}]},
    ]


def _build_footer(payload: "AlertPayload") -> "dict[str, Any]":
    ts = payload.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": f":clock1: {ts}"}]}

import json
import os
import sys

from heartbeat.checker import HealthChecker
from heartbeat.config import HeartbeatConfig
from heartbeat.models import AlertPayload, AlertState, HealthResult, HealthStatus
from heartbeat.notifier import SlackNotifier

_STATUS_ICON = {
    HealthStatus.HEALTHY: "✓",
    HealthStatus.UNHEALTHY: "✗",
    HealthStatus.DEGRADED: "!",
    HealthStatus.TIMEOUT: "T",
    HealthStatus.ERROR: "✗",
}


class HeartbeatRunner:
    def __init__(self, config: "HeartbeatConfig") -> None:
        self._config = config

    async def run(self) -> "list[HealthResult]":
        """
        runs the health checks for all configured services, prints the results,
        sets GitHub Actions outputs, and sends notifications if any services are unhealthy.
        """
        async with HealthChecker() as checker:
            results = await checker.check_all(self._config.services)

        self._print_results(results)
        self._set_github_output(results)

        unhealthy = [r for r in results if not r.is_ok]
        if unhealthy:
            await self._notify(results)

        return results

    async def _notify(self, results: "list[HealthResult]") -> None:
        """
        notifies via Slack if any services are unhealthy or degraded, summarizing the results.
        """
        if not self._config.slack_webhook_url:
            return
        unhealthy_count = sum(1 for r in results if not r.is_ok)
        degraded_count = sum(1 for r in results if r.status == HealthStatus.DEGRADED)
        parts = []
        if unhealthy_count - degraded_count:
            parts.append(f"{unhealthy_count - degraded_count} down")
        if degraded_count:
            parts.append(f"{degraded_count} degraded")
        summary = ", ".join(parts) + f" out of {len(results)} services"

        payload = AlertPayload(
            state=AlertState.FIRING,
            results=tuple(results),
            summary=summary,
        )
        notifier = SlackNotifier(self._config.slack_webhook_url)
        await notifier.send(payload)

    def _print_results(self, results: "list[HealthResult]") -> None:
        """
        simply prints the health check results to the console in a tabular format, including service name,
        status, HTTP code, and response time.
        """
        print(f"\n{'Service':<30} {'Status':<12} {'Code':<6} {'Time (ms)':<12}")
        print("-" * 65)
        for r in results:
            icon = _STATUS_ICON.get(r.status, "?")
            code = str(r.status_code) if r.status_code is not None else "-"
            time_ms = f"{r.response_time_ms:.0f}" if r.response_time_ms is not None else "-"
            print(f"{r.service.name:<30} {icon} {r.status.value:<10} {code:<6} {time_ms:<12}")
            if r.error_message:
                print(f"  └─ {r.error_message}")
        print()

        for r in results:
            if not r.is_ok:
                print(f"::error::Service '{r.service.name}' is {r.status.value.upper()}", file=sys.stderr)
            elif r.status == HealthStatus.DEGRADED:
                print(f"::warning::Service '{r.service.name}' is DEGRADED", file=sys.stderr)

    def _set_github_output(self, results: "list[HealthResult]") -> None:
        """
        sets GitHub Actions outputs for the overall health status and detailed results in JSON format,
        which can be used in subsequent steps of the workflow.
        """
        output_file = os.environ.get("GITHUB_OUTPUT")
        if not output_file:
            return

        all_ok = all(r.is_ok for r in results)
        results_json = json.dumps(
            [
                {
                    "name": r.service.name,
                    "status": r.status.value,
                    "status_code": r.status_code,
                    "response_time_ms": r.response_time_ms,
                    "error_message": r.error_message,
                }
                for r in results
            ]
        )

        with open(output_file, "a") as f:
            f.write(f"healthy={str(all_ok).lower()}\n")
            f.write(f"results={results_json}\n")

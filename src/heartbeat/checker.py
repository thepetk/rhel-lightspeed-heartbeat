from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from typing import Self

import httpx

from heartbeat.models import HealthResult, HealthStatus, ServiceConfig


class HealthChecker:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def check(self, service: ServiceConfig) -> HealthResult:
        assert self._client is not None, "HealthChecker must be used as an async context manager"
        url = f"{service.url.rstrip('/')}{service.health_path}"
        start = time.monotonic()
        try:
            response = await self._client.get(url, timeout=service.timeout_seconds)
            elapsed_ms = (time.monotonic() - start) * 1000

            if response.status_code not in service.expected_status_codes:
                return HealthResult(
                    service=service,
                    status=HealthStatus.UNHEALTHY,
                    status_code=response.status_code,
                    response_time_ms=elapsed_ms,
                )

            if service.response_time_threshold_ms is not None and elapsed_ms > service.response_time_threshold_ms:
                return HealthResult(
                    service=service,
                    status=HealthStatus.DEGRADED,
                    status_code=response.status_code,
                    response_time_ms=elapsed_ms,
                )

            return HealthResult(
                service=service,
                status=HealthStatus.HEALTHY,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
            )

        except httpx.TimeoutException:
            elapsed_ms = (time.monotonic() - start) * 1000
            return HealthResult(
                service=service,
                status=HealthStatus.TIMEOUT,
                response_time_ms=elapsed_ms,
                error_message=f"Request timed out after {service.timeout_seconds}s",
            )
        except httpx.HTTPError as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            return HealthResult(
                service=service,
                status=HealthStatus.ERROR,
                response_time_ms=elapsed_ms,
                error_message=str(e),
            )

    async def check_all(self, services: Sequence[ServiceConfig]) -> list[HealthResult]:
        return list(await asyncio.gather(*[self.check(s) for s in services]))

    async def __aenter__(self) -> Self:
        if self._owns_client:
            self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

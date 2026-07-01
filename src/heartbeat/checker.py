import asyncio
import os
import time
from collections.abc import Sequence
from typing import Any, Self

import httpx

from heartbeat.models import AuthConfig, HealthResult, HealthStatus, ServiceConfig


class HealthChecker:
    def __init__(self, client: "httpx.AsyncClient | None" = None) -> "None":
        self._client = client
        self._owns_client = client is None

    async def check(self, service: "ServiceConfig") -> "HealthResult":
        """
        checks the health of a service, retrying up to service.retry_count times
        with exponential backoff on any non-HEALTHY result.
        """
        if service.auth is not None or service.proxy is not None:
            client = _build_client(service)
            try:
                result = await self._check_once(service, client)
                for attempt in range(service.retry_count):
                    if result.status == HealthStatus.HEALTHY:
                        return result
                    await asyncio.sleep(service.backoff_base_seconds * (2**attempt))
                    result = await self._check_once(service, client)
                return result
            finally:
                await client.aclose()
        else:
            assert self._client is not None, "HealthChecker must be used as an async context manager"
            result = await self._check_once(service, self._client)
            for attempt in range(service.retry_count):
                if result.status == HealthStatus.HEALTHY:
                    return result
                await asyncio.sleep(service.backoff_base_seconds * (2**attempt))
                result = await self._check_once(service, self._client)
            return result

    async def _check_once(self, service: "ServiceConfig", client: "httpx.AsyncClient") -> "HealthResult":
        url = f"{service.url.rstrip('/')}{service.health_path}"
        kwargs: dict[str, Any] = {"timeout": service.timeout_seconds}
        if service.body is not None:
            kwargs["json"] = service.body
        start = time.monotonic()
        try:
            response = await client.request(service.method, url, **kwargs)
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

    async def check_all(self, services: "Sequence[ServiceConfig]") -> "list[HealthResult]":
        return list(await asyncio.gather(*[self.check(s) for s in services]))

    async def __aenter__(self) -> "Self":
        if self._owns_client:
            self._client = httpx.AsyncClient(follow_redirects=True)
        return self

    async def __aexit__(self, *_: "object") -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None


def _build_client(service: "ServiceConfig") -> "httpx.AsyncClient":
    kwargs: dict[str, Any] = {"follow_redirects": True}

    if service.proxy is not None:
        kwargs["proxy"] = service.proxy

    if service.auth is not None:
        _apply_auth(kwargs, service.auth)

    return httpx.AsyncClient(**kwargs)


def _apply_auth(kwargs: "dict[str, Any]", auth: "AuthConfig") -> None:
    if auth.type == "mtls":
        kwargs["cert"] = (auth.cert_path, auth.key_path)
    elif auth.type == "saml_session":
        assert auth.token_env_var is not None
        token = os.environ.get(auth.token_env_var)
        if not token:
            raise ValueError(f"SAML session token env var '{auth.token_env_var}' is not set or empty")
        kwargs["cookies"] = {"session": token}

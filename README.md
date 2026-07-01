# Heartbeat

A CLI tool that probes service health endpoints concurrently and sends Slack alerts formatted like Prometheus Alertmanager notifications when something is down or degraded.

## Quick Start

### Run locally

```bash
git clone https://github.com/thepetk/heartbeat
cd heartbeat
pip install .

cp config.example.yaml config.yaml
# edit config.yaml with your services
heartbeat config.yaml
```

### Run as a container

```bash
docker build -f Containerfile -t heartbeat .
docker run -v $(pwd)/config.yaml:/app/config.yaml heartbeat
```

Pass the Slack webhook via environment variable to avoid putting it in the config file:

```bash
docker run \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -e HEARTBEAT_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... \
  heartbeat
```

## Configuration

Create a YAML config file (see `config.example.yaml`):

```yaml
services:
  - name: api
    url: https://api.example.com
  - name: gateway
    url: https://gateway.example.com
    health_path: /health
    response_time_threshold_ms: 500

# slack_webhook_url: https://hooks.slack.com/...
# Or set the HEARTBEAT_SLACK_WEBHOOK_URL environment variable instead.

timeout: 10
fail_on_unhealthy: true
retry_count: 5
backoff_base_seconds: 1.0
```

### Top-level fields

| Field                  | Required | Default  | Description                                                    |
| ---------------------- | -------- | -------- | -------------------------------------------------------------- |
| `services`             | Yes      | —        | List of service definitions (see format below)                 |
| `slack_webhook_url`    | No       | `null`   | Slack incoming webhook URL (overridden by env var, see below)  |
| `timeout`              | No       | `10`     | Default HTTP probe timeout in seconds                          |
| `fail_on_unhealthy`    | No       | `true`   | Exit with code 1 if any service is unhealthy or degraded       |
| `retry_count`          | No       | `5`      | Default number of retries per service before marking as failed |
| `backoff_base_seconds` | No       | `1.0`    | Base delay in seconds for exponential backoff between retries  |

### Service fields

| Field                        | Required | Default      | Description                                                                      |
| ---------------------------- | -------- | ------------ | -------------------------------------------------------------------------------- |
| `name`                       | Yes      | —            | Display name for the service                                                     |
| `url`                        | Yes      | —            | Base URL of the service (without the health path)                                |
| `health_path`                | No       | `"/healthz"` | Path to append to `url` for the health check request                             |
| `method`                     | No       | `"GET"`      | HTTP method to use (`GET`, `POST`, etc.)                                         |
| `body`                       | No       | omit         | JSON object to send as the request body (sets `Content-Type: application/json`)  |
| `proxy`                      | No       | omit         | HTTP proxy URL (e.g. `http://squid.corp.redhat.com:3128`)                        |
| `timeout_seconds`            | No       | `10.0`       | Per-service HTTP timeout in seconds                                              |
| `expected_status_codes`      | No       | `[200]`      | List of HTTP status codes that indicate healthy                                  |
| `response_time_threshold_ms` | No       | omit         | If set, responses slower than this are marked DEGRADED                           |
| `retry_count`                | No       | global       | Per-service override for number of retries                                       |
| `backoff_base_seconds`       | No       | global       | Per-service override for backoff base delay                                      |
| `auth`                       | No       | omit         | Authentication block (see below)                                                 |

### Auth block

Set `auth` on a service to enable authentication. Two types are supported:

**mTLS** — client certificate authentication:

```yaml
auth:
  type: mtls
  cert_path: /etc/pki/consumer/cert.pem
  key_path: /etc/pki/consumer/key.pem
```

`cert_path` and `key_path` must point to existing files on disk (validated at startup).

**SAML session cookie** — sets a `session` cookie from an environment variable:

```yaml
auth:
  type: saml_session
  token_env_var: MY_SAML_SESSION_TOKEN   # name of the env var holding the token
```

The token is read at runtime from the env var named by `token_env_var`. This allows different services to use different tokens. Heartbeat raises an error at check time if the env var is not set.

### Environment variables

| Variable                     | Description                                                        |
| ---------------------------- | ------------------------------------------------------------------ |
| `HEARTBEAT_SLACK_WEBHOOK_URL`| Overrides `slack_webhook_url` from the config file if set          |
| *(any name)*                 | Used by `saml_session` auth — name specified in `auth.token_env_var` |

### Running with certificates in a container

Mount the cert directory as a read-only volume:

```bash
docker run \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v /etc/pki/consumer:/etc/pki/consumer:ro \
  -e HEARTBEAT_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... \
  heartbeat
```

## Health Statuses

| Status      | Meaning                                                               |
| ----------- | --------------------------------------------------------------------- |
| `HEALTHY`   | Service responded within time and with an expected status code        |
| `DEGRADED`  | Service responded correctly but exceeded `response_time_threshold_ms` |
| `UNHEALTHY` | Service responded with an unexpected status code                      |
| `TIMEOUT`   | Request timed out                                                     |
| `ERROR`     | Network or connection error                                           |

`fail_on_unhealthy` causes a non-zero exit for any status that is not HEALTHY or DEGRADED. DEGRADED services emit a `WARNING:` message to stderr but do not fail.

Any non-HEALTHY result triggers the retry logic. The delay between attempts follows exponential backoff: `backoff_base_seconds × 2^attempt` (1 s, 2 s, 4 s, … with the default 1.0 s base). A Slack alert is only sent if all retries are exhausted and the service is still not healthy.

## Slack Alert Format

When one or more services are not ok, the tool posts a Slack message with:

- Red sidebar (`#EE0000`) for firing alerts, green (`#36A64F`) for resolved
- `[FIRING:N]` header counting affected services
- Per-service section with status emoji, HTTP code, response time, threshold, and error detail
- Footer with timestamp

Example alert structure:

```
🚨 [FIRING:2] Heartbeat
Alert: ServiceDown    Summary: 1 down, 1 degraded out of 3 services
────────────────────────────────────────
Service: api          Status: ✗ UNHEALTHY (HTTP 503)
  Response time: 245ms | URL: https://api.example.com/healthz

Service: backend      Status: ⚠ DEGRADED (HTTP 200)
  Response time: 3120ms | Threshold: 2000ms | URL: https://backend.example.com/healthz
────────────────────────────────────────
🕐 2026-06-30T12:00:00Z
```

## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/) >= 0.4
- Python 3.13+

### Setup

```bash
git clone https://github.com/thepetk/heartbeat
cd heartbeat
make install
```

### Make Targets

| Target              | Description                                               |
| ------------------- | --------------------------------------------------------- |
| `make install`      | Install dependencies with uv                             |
| `make lint`         | Run ruff linter                                           |
| `make format`       | Check formatting with ruff                                |
| `make format-fix`   | Auto-fix formatting                                       |
| `make type-check`   | Run ty type checker                                       |
| `make test`         | Run tests                                                 |
| `make test-cov`     | Run tests with coverage report                            |
| `make run`          | Run heartbeat locally (requires `config.yaml`)            |
| `make container-build` | Build container image                                  |
| `make check`        | Run all checks (lint, format, types, tests with coverage) |
| `make clean`        | Remove build artifacts and caches                         |

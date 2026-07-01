# Heartbeat

A GitHub Action that probes service health endpoints concurrently and sends Slack alerts formatted like Prometheus Alertmanager notifications when something is down or degraded.

## Quick Start

### As a GitHub Action

```yaml
- uses: thepetk/heartbeat@main
  with:
    services: |
      - name: api
        url: https://api.example.com
      - name: gateway
        url: https://gateway.example.com
        health_path: /health
      - name: backend
        url: https://backend.example.com
        response_time_threshold_ms: 2000
    slack_webhook_url: ${{ secrets.SLACK_WEBHOOK_URL }}
```

### Use outputs in subsequent steps

```yaml
- id: heartbeat
  uses: thepetk/heartbeat@main
  with:
    services: |
      - name: api
        url: https://api.example.com
    fail_on_unhealthy: "false"

- run: echo "All healthy? ${{ steps.heartbeat.outputs.healthy }}"
- run: echo "Results JSON: ${{ steps.heartbeat.outputs.results }}"
```

### Run locally

```bash
export HEARTBEAT_SERVICES='
- name: httpbin
  url: https://httpbin.org
  health_path: /status/200
'
# Optional:
export HEARTBEAT_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

uv run python -m heartbeat
```

## Configuration

### Action Inputs

| Input                   | Required | Default  | Description                                                    |
| ----------------------- | -------- | -------- | -------------------------------------------------------------- |
| `services`              | Yes      | —        | YAML sequence of service definitions (see format below)        |
| `slack_webhook_url`     | No       | `""`     | Slack incoming webhook URL for failure notifications           |
| `timeout`               | No       | `"10"`   | Default HTTP probe timeout in seconds                          |
| `fail_on_unhealthy`     | No       | `"true"` | Exit with failure code if any service is unhealthy or degraded |
| `retry_count`           | No       | `"5"`    | Number of retries per service before marking it as failed      |
| `backoff_base_seconds`  | No       | `"1.0"`  | Base delay in seconds for exponential backoff between retries  |

### Action Outputs

| Output    | Type                 | Description                                                         |
| --------- | -------------------- | ------------------------------------------------------------------- |
| `healthy` | `"true"` / `"false"` | Whether all services are healthy (HEALTHY or DEGRADED counts as ok) |
| `results` | JSON string          | Array of per-service check results                                  |

### Services YAML Format

Each service entry in the `services` sequence supports:

| Field                        | Required | Default      | Description                                            |
| ---------------------------- | -------- | ------------ | ------------------------------------------------------ |
| `name`                       | Yes      | —            | Display name for the service                           |
| `url`                        | Yes      | —            | Base URL of the service (without the health path)      |
| `health_path`                | No       | `"/healthz"` | Path to append to `url` for the health check request   |
| `timeout_seconds`            | No       | `10.0`       | Per-service HTTP timeout in seconds                    |
| `expected_status_codes`      | No       | `[200]`      | List of HTTP status codes that indicate healthy        |
| `response_time_threshold_ms` | No       | omit         | If set, responses slower than this are marked DEGRADED |

### Environment Variables (local use)

| Variable                      | Description                     |
| ----------------------------- | ------------------------------- |
| `HEARTBEAT_SERVICES`          | Same format as `services` input |
| `HEARTBEAT_SLACK_WEBHOOK_URL` | Slack webhook URL               |
| `HEARTBEAT_TIMEOUT`           | Default timeout in seconds      |
| `HEARTBEAT_FAIL_ON_UNHEALTHY` | `"true"` / `"false"`            |

## Health Statuses

| Status      | Meaning                                                               |
| ----------- | --------------------------------------------------------------------- |
| `HEALTHY`   | Service responded within time and with an expected status code        |
| `DEGRADED`  | Service responded correctly but exceeded `response_time_threshold_ms` |
| `UNHEALTHY` | Service responded with an unexpected status code                      |
| `TIMEOUT`   | Request timed out                                                     |
| `ERROR`     | Network or connection error                                           |

`fail_on_unhealthy` causes a non-zero exit for any status that is not HEALTHY or DEGRADED. DEGRADED services emit a `::warning::` annotation but do not fail the action.

## Slack Alert Format

When one or more services are not ok, the action posts a Slack message with:

- Red sidebar (`#EE0000`) for firing alerts, green (`#36A64F`) for resolved
- `[FIRING:N]` header counting affected services
- Per-service section with status emoji, HTTP code, response time, threshold, and error detail
- Footer with timestamp and link to the GitHub Actions run

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
🕐 2026-06-30T12:00:00Z | GitHub Actions Run #123
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

| Target            | Description                                               |
| ----------------- | --------------------------------------------------------- |
| `make install`    | Install dependencies with uv                              |
| `make lint`       | Run ruff linter                                           |
| `make format`     | Check formatting with ruff                                |
| `make format-fix` | Auto-fix formatting                                       |
| `make type-check` | Run ty type checker                                       |
| `make test`       | Run tests                                                 |
| `make test-cov`   | Run tests with coverage report                            |
| `make run`        | Run heartbeat locally (requires `HEARTBEAT_SERVICES`)     |
| `make check`      | Run all checks (lint, format, types, tests with coverage) |
| `make clean`      | Remove build artifacts and caches                         |

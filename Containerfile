FROM registry.access.redhat.com/ubi10/ubi-minimal:10.2-1782798957

LABEL name="heartbeat" \
      summary="Health check probe for services with Slack alerting" \
      description="Probes service health endpoints concurrently and sends Slack alerts when something is down or degraded."

RUN microdnf install -y python3 python3-pip && \
    microdnf clean all

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

RUN python3 -m pip install --no-cache-dir .

ENTRYPOINT ["heartbeat"]
CMD ["config.yaml"]

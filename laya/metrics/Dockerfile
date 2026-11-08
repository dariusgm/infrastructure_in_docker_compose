# Metrics proxy in front of laya-serve (see proxy.py and laya/README.md).
FROM python:3.11-slim-trixie

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install "prometheus-client==0.22.1" && pip check

RUN groupadd --gid 10002 lproxy \
    && useradd --uid 10002 --gid lproxy --no-create-home --shell /usr/sbin/nologin lproxy

COPY proxy.py /opt/laya-metrics/proxy.py

USER lproxy
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/metrics', timeout=4)"

ENTRYPOINT ["python", "/opt/laya-metrics/proxy.py"]

# cosmoes.org on Cloud Run: one process, listening on $PORT (Cloud Run sets it; 8080 otherwise). The specifications
# ship in the image (site/specs/): no storage, no secrets, no environment.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY cosmoes ./cosmoes
COPY site ./site
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin cosmoes
USER cosmoes

EXPOSE 8080
# Cloud Run's front end terminates TLS and sets X-Forwarded-*; uvicorn trusts it, so the app sees https and sends HSTS.
CMD ["sh", "-c", "exec uvicorn cosmoes.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]

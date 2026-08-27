FROM python:3.13.14-slim-bookworm AS runtime

ARG APP_VERSION=development
ARG APP_GIT_SHA=unknown
LABEL org.opencontainers.image.title="Tandem TVS backend" \
    org.opencontainers.image.version=$APP_VERSION \
    org.opencontainers.image.revision=$APP_GIT_SHA

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app --no-create-home app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --chown=app:app . .
RUN mkdir -p /app/media \
    && chown app:app /app/media \
    && chmod 0755 /app/media \
    && chmod +x /app/entrypoint.sh

EXPOSE 8000
USER app
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uv", "run", "--no-sync", "uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "6", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1,172.31.251.0/29", "--ws-max-size", "512", "--no-access-log"]

FROM python:3.13.14-slim-bookworm AS runtime

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
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
USER app
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uv", "run", "--no-sync", "uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--ws-max-size", "512", "--no-access-log"]

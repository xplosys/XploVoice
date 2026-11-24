# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
# API image: FastAPI on uvicorn, non-root, dependencies pinned by uv.lock.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
# pip is not needed at runtime and carries its own vendored libraries; remove it to shrink the attack surface.
RUN python -m pip uninstall -y pip setuptools wheel 2>/dev/null; rm -rf /usr/local/lib/python3.13/site-packages/pip* \
    && useradd --system --uid 10001 --home /app xplovoice
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "xplovoice_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

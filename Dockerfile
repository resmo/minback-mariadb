# mariadb provides mariadb-dump; the app itself is Python, installed with uv.
FROM mariadb:lts
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -y update \
    && apt-get install -y --no-install-recommends ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY minback ./minback
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    uv sync --frozen --no-dev --no-editable

# Configuration defaults live in minback/config.py; see README.md.
ENV PYTHONUNBUFFERED=1

EXPOSE 8080
ENTRYPOINT ["/opt/venv/bin/minback"]
CMD ["run"]

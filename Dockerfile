FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY data/league ./data/league
COPY data/season ./data/season
COPY src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist
EXPOSE 8000
CMD ["/app/.venv/bin/databall-serve", "--data", "data/league", "--port", "8000", "--web", "web/dist"]

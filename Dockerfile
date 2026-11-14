# One image serves the API and the built console from the same origin.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
# Empty base: the console calls the origin that served it.
ARG VITE_AGENT_MODEL=replay
RUN VITE_API_BASE= VITE_AGENT_MODEL=$VITE_AGENT_MODEL npm run build

FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY datasets ./datasets
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist

ENV PATH="/app/.venv/bin:$PATH"
ENV ALERT2ATTACK_OLLAMA_BASE_URL=http://ollama:11434/v1
ENV ALERT2ATTACK_API_HOST=0.0.0.0
ENV ALERT2ATTACK_API_PORT=8000
ENV ALERT2ATTACK_WEB_DIST=/app/web/dist

EXPOSE 8000

CMD ["uvicorn", "alert2attack.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

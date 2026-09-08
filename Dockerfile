FROM node:24.20.0-bookworm-slim AS frontend-development
WORKDIR /app/frontend
RUN npm install --global pnpm@11.19.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]

FROM frontend-development AS frontend-build
RUN pnpm build

FROM python:3.12.14-slim-bookworm AS backend-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update \
    && apt-get install --yes --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY backend/ ./backend/
RUN python -m pip install --no-cache-dir -c backend/constraints.txt ./backend

FROM backend-base AS backend-development
RUN python -m pip install --no-cache-dir -c backend/constraints.txt -e './backend[dev]'
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/backend/app"]

FROM backend-base AS production
ENV TTB_ENVIRONMENT=production \
    TTB_CORS_ORIGINS=[] \
    TTB_FRONTEND_DIST=/app/frontend/dist
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

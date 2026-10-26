FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY skills ./skills
RUN pip install --no-cache-dir .
COPY --from=web /web/dist ./frontend/dist
RUN useradd --create-home supportflow && mkdir /app/data && chown supportflow:supportflow /app/data
USER supportflow
ENV SUPPORTFLOW_ROOT=/app SUPPORTFLOW_HOST=0.0.0.0 SUPPORTFLOW_PORT=8010 SUPPORTFLOW_DATA_DIR=/app/data
EXPOSE 8010
CMD ["support-flow"]

FROM node:22-alpine AS web-build
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.28-alpine AS web
COPY --from=web-build /web/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

FROM python:3.12-slim AS api
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY skills ./skills
ARG SUPPORTFLOW_PYTHON_EXTRAS=postgres
RUN pip install --no-cache-dir ".[${SUPPORTFLOW_PYTHON_EXTRAS}]"
# Retain the all-in-one image entry for local Docker use; Compose's web service
# serves these assets directly and proxies API/SSE requests to this process.
COPY --from=web-build /web/dist ./frontend/dist
RUN useradd --create-home supportflow && mkdir /app/data && chown supportflow:supportflow /app/data
USER supportflow
ENV SUPPORTFLOW_ROOT=/app SUPPORTFLOW_HOST=0.0.0.0 SUPPORTFLOW_PORT=8000 SUPPORTFLOW_DATA_DIR=/app/data
EXPOSE 8000
CMD ["support-flow"]

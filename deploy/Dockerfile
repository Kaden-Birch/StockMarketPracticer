# AIPTP server image — build from the repository root:
#   docker build -f deploy/Dockerfile -t aiptp/server .
#
# Behind a TLS-inspecting corporate proxy, pass its CA as a build secret
# (never disable TLS verification):
#   docker build --secret id=extra_ca,src=/path/to/proxy-ca.crt -f deploy/Dockerfile .

# The extra_ca secret must be a FULL CA bundle (public roots + your proxy CA);
# it is only consulted during network-using build steps and never baked into
# the image.

# --- frontend build stage ---
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=extra_ca,required=false \
    sh -c 'if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; \
             npm config set cafile /run/secrets/extra_ca; fi; \
           npm ci --no-audit --no-fund'
COPY frontend/ ./
RUN npm run build

# --- runtime stage ---
FROM python:3.12-slim
WORKDIR /app

COPY backend/ backend/
RUN --mount=type=secret,id=extra_ca,required=false \
    sh -c 'if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
           pip install --no-cache-dir ./backend'

COPY --from=frontend /build/frontend/dist frontend/dist

ENV AIPTP_HOST=0.0.0.0 \
    AIPTP_PORT=8420 \
    AIPTP_DATA_DIR=/data \
    AIPTP_AUTH=required \
    AIPTP_FRONTEND_DIR=/app/frontend/dist

VOLUME /data
EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; \
      sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8420/api/v1/health', timeout=4).status==200 else 1)"

CMD ["aiptp"]

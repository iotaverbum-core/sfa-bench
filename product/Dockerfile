# GroundLedger — in-VPC deploy. Stdlib only: no pip install, no network egress.
#
#   docker build -t groundledger -f product/Dockerfile .
#   docker run -p 8000:8000 -v gl-data:/data \
#     -e GROUNDLEDGER_API_KEYS="prod-key:acme-insurance" \
#     -e GROUNDLEDGER_SIGNING_KEYS="acme-insurance:CHANGE_ME" \
#     groundledger
#
# Then: curl -s -X POST http://localhost:8000/v1/verify \
#   -H 'X-API-Key: prod-key' --data @product/examples/grounded_answer.json
FROM python:3.11-slim

WORKDIR /app

# The product reuses the deterministic sfa core; copy both packages and the
# taxonomy file. No third-party dependencies are installed.
COPY sfa ./sfa
COPY families.json ./families.json
COPY product ./product

ENV GROUNDLEDGER_HOST=0.0.0.0 \
    GROUNDLEDGER_PORT=8000 \
    GROUNDLEDGER_DATA=/data \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["python", "-m", "product.groundledger.api"]

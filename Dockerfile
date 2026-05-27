FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY config/ ./config/
COPY docs/ ./docs/
COPY src/ ./src/
COPY web/ ./web/
COPY run_screener.py screener README.md ./

RUN mkdir -p data/raw data/processed data/web_workspace logs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import base64, json, os, urllib.request; req=urllib.request.Request('http://127.0.0.1:8765/api/readiness'); auth=os.environ.get('CANSLIM_DASHBOARD_AUTH'); req.add_header('Authorization', 'Basic ' + base64.b64encode(auth.encode()).decode()) if auth else None; data=json.load(urllib.request.urlopen(req, timeout=3)); raise SystemExit(0 if data.get('ok') else 1)"

CMD ["python", "run_screener.py", "--mode", "web", "--host", "0.0.0.0", "--port", "8765", "--allow-remote", "--require-auth", "--quiet"]

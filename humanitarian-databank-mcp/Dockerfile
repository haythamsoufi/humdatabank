FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn

COPY databank_client.py databank_analytics.py instructions.py server.py ./
COPY assets/ ./assets/

ENV MCP_TRANSPORT=streamable-http
ENV DATABANK_API_BASE=https://databank.ifrc.org/api/v1

EXPOSE 8000

CMD gunicorn server:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}

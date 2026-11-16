# Container for the portal on a small server (see "Deploy" in README.md).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p data/uploads && useradd --create-home portal && chown -R portal /app
USER portal

EXPOSE 8501
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pitch_pipeline ./pitch_pipeline
COPY run_pipeline.py config.docker.json synthetic_generator.py ./

RUN useradd --create-home appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

USER appuser

CMD ["python", "run_pipeline.py", "--config", "config.docker.json"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Embedding modeli burada tutulur (docker-compose'da kalıcı volume).
    HF_HOME=/models

WORKDIR /code

# Yalnızca CPU'lu torch: GPU sürümünden birkaç GB küçük; embedding için yeterli.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir ".[embeddings,transcription]"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

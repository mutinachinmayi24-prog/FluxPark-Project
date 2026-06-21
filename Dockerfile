# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite database lives here at runtime (git-ignored, mount as a volume)
RUN mkdir -p instance

EXPOSE 8000

# Override with a strong, unique value at runtime (see .env.example)
ENV SECRET_KEY=change-this-to-a-long-random-secret-key

# Single worker: SQLite + multiple processes racing on startup table
# creation (and concurrent writes) isn't safe, so we don't scale workers here.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

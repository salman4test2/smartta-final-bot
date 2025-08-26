FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
ENV PORT=8000
CMD ["bash", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]

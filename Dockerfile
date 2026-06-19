FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 데이터 디렉토리 생성 (Fly.io 볼륨 마운트 포인트)
RUN mkdir -p /data

ENV FLASK_ENV=production
ENV DB_PATH=/data/news.db

EXPOSE 8080

CMD ["python", "app.py"]

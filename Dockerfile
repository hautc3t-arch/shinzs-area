FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg nodejs npm --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html cookies.txt ./

EXPOSE 10000
CMD ["python", "app.py"]

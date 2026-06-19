FROM python:3.11-slim

# Node.js 20 LTS + ffmpeg
RUN apt-get update && apt-get install -y curl ffmpeg --no-install-recommends && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Verify yt-dlp-ejs được cài đúng
RUN python3 -c "import yt_dlp_ejs; print('yt-dlp-ejs OK:', yt_dlp_ejs.__file__)"
RUN node --version && python3 -m yt_dlp --version

COPY app.py index.html cookies.txt ./

# Test JS runtime detection
RUN python3 -m yt_dlp --js-runtimes node --version

EXPOSE 10000
CMD ["python", "app.py"]

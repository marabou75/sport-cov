# api/Dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libharfbuzz0b \
    libfribidi0 \
    libfreetype6 \
    libfontconfig1 \
    libjpeg62-turbo \
    libpng16-16 \
    libxml2 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]

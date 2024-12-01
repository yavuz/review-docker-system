FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    cron \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# Gereksinimleri yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --upgrade pip

# Cronjob dosyasını kopyala ve crontab'e ekle
COPY cronjob /etc/cron.d/cronjob
RUN chmod 0644 /etc/cron.d/cronjob
RUN crontab /etc/cron.d/cronjob

# Python dosyalarını kopyala
COPY . .

# Ensure the cron log file exists
RUN touch /var/log/cron.log

# Run cron and tail the log file
CMD cron && tail -f /var/log/cron.log

FROM python:3.11-slim

# Arbeitsverzeichnis festlegen
WORKDIR /app

# Systemabhängigkeiten & Zeitzone
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Python Abhängigkeiten installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Anwendungsquellcode kopieren
COPY app/ /app/app/
COPY config/ /app/config/
COPY esphome/ /app/esphome/

# Datenverzeichnis für SQLite und Config vorbereiten
RUN mkdir -p /app/data

# Port des Web-Dashboards
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/api/system/status || exit 1

# Startbefehl
CMD ["python", "-m", "app.main"]

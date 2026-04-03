# LibreTranslate setup

LibreTranslate is an optional translation service that can be enabled for automatic translations. It supports: English, French, Spanish, Arabic, Chinese, Russian, Hindi.

**Note:** LibreTranslate is disabled by default. To enable it, follow the setup below.

## Enabling LibreTranslate

### 1. Add the LibreTranslate service to Docker Compose

Add a LibreTranslate service to your Docker Compose file (e.g. project root `docker-compose.yml` or a custom compose file):

```yaml
libretranslate:
  image: libretranslate/libretranslate:latest
  container_name: libretranslate
  ports:
    - "5000:5000"
  volumes:
    - libretranslate_data:/app/data
  environment:
    - LT_UPDATE_MODELS=true
    - LT_LOAD_ONLY=en,fr,es,ar,zh,ru,hi
  restart: unless-stopped
```

### 2. Add LibreTranslate as a dependency of the backend service

In your backend (Backoffice) service:

```yaml
depends_on:
  db:
    condition: service_healthy
  db-init:
    condition: service_completed_successfully
  libretranslate:
    condition: service_started
```

### 3. Set the LibreTranslate URL in the backend environment

```yaml
environment:
  - FLASK_CONFIG=production
  - DATABASE_URL=postgresql://app:app@db:5432/ngo_databank
  - LIBRETRANSLATE_URL=http://libretranslate:5000
```

### 4. Restart the services

From the directory containing your compose file:

```bash
docker-compose down
docker-compose up -d
```

## Environment variable (non-Docker)

Add the LibreTranslate URL to your `.env` file in the Backoffice directory:

```bash
# Optional: LibreTranslate
LIBRETRANSLATE_URL=http://libretranslate:5000
```

- **Docker setups:** use `http://libretranslate:5000` (service name).
- **Manual/local setups:** use `http://127.0.0.1:5001` or your LibreTranslate instance URL.

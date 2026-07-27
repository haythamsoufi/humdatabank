FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt ./
# Install without cache to save space, and use --no-cache-dir
# Install CPU-only PyTorch first to avoid downloading 4-5GB of CUDA libraries
# (Azure App Service doesn't have GPU support, so CUDA is never used)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Final stage - minimal runtime image
FROM python:3.11-slim

ARG ASSET_VERSION=""
ARG GIT_SHA=""
ARG RELEASE_VERSION=""
# Latest GitHub release tag at build time (deploy workflow); admin UI / update check only.
ARG LATEST_RELEASE_TAG=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_CONFIG=development \
    FLASK_APP="run:app"

# Only runtime dependencies (no build tools)
# Include WeasyPrint system dependencies: Cairo, Pango, GDK-PixBuf, and related libraries
# Also include fonts for proper PDF text rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
    openssh-server \
    && echo "root:Docker!" | chpasswd \
    && mkdir -p /var/run/sshd \
    && ssh-keygen -A \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . /app

# Extract translatable strings from source, update PO files, compile .mo,
# then snapshot as translations_base/ for the persistent-volume sync script.
# Running extraction here ensures translations_base/ always matches the source
# code in the image, even when developers forget to commit updated .po files
# before building — preventing newly-added strings from being incorrectly
# marked as obsolete by sync_persistent_translations.py on next deploy.
RUN python scripts/extract_update_translations.py --compile && \
    cp -a /app/translations /app/translations_base

# Ensure static files are properly accessible
RUN mkdir -p /app/app/static && \
    chmod -R 755 /app/app/static

# Create uploads directory for persistent storage
RUN mkdir -p /data/uploads && \
    chmod 755 /data/uploads

# Entrypoint script (runs migrations at container startup, not at build time)
COPY entrypoint.sh /app/entrypoint.sh
COPY sshd_config /etc/ssh/sshd_config
COPY docker/azure-ssh-profile.sh /etc/profile.d/azure-ssh.sh
RUN chmod +x /app/entrypoint.sh /etc/profile.d/azure-ssh.sh \
    && printf '%s\n' \
       '# Azure App Service SSH defaults (fallback when shell is not a login shell)' \
       '[ -f /etc/profile.d/azure-ssh.sh ] && . /etc/profile.d/azure-ssh.sh' \
       >> /root/.bashrc

EXPOSE 5000 2222

# Set version identifiers last so they don't invalidate cached layers above.
# APP_VERSION = semver from GitHub releases/latest (CI). RELEASE_VERSION = image tag stream (e.g. v1.7).
ENV ASSET_VERSION=${ASSET_VERSION} \
    GIT_SHA=${GIT_SHA} \
    RELEASE_VERSION=${RELEASE_VERSION} \
    APP_VERSION=${LATEST_RELEASE_TAG}

# Always run our entrypoint first (so migrations happen even if Azure overrides the command)
ENTRYPOINT ["/app/entrypoint.sh"]

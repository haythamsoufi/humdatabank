#!/bin/bash
set -e

echo "=========================================="
echo "Starting Humanitarian Databank on Azure"
echo "=========================================="

# Print environment info
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo "FLASK_CONFIG: ${FLASK_CONFIG}"

# Ensure upload directory exists
echo "Setting up upload directory..."
mkdir -p /home/site/wwwroot/uploads
chmod 755 /home/site/wwwroot/uploads
echo "✓ Upload directory ready"

# Install Node.js dependencies if not already installed
if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install --production
    echo "✓ Node.js dependencies installed"
fi

# Build Tailwind CSS
echo "Building CSS assets..."
npm run build:css
echo "✓ CSS assets built successfully"

# Run database migrations
echo "Running database migrations..."
export FLASK_APP=run:app
python -m flask db upgrade
echo "✓ Database migrations completed"

# Start application with Gunicorn
echo "=========================================="
echo "Starting Gunicorn WSGI server..."
echo "Workers: 4, Threads: 2, Timeout: 120s"
echo "=========================================="

# Use config file if it exists, otherwise use command-line args
if [ -f "config/gunicorn.conf.py" ]; then
    echo "Using config/gunicorn.conf.py for configuration"
    exec gunicorn --config config/gunicorn.conf.py run:app
else
    # Fallback to command-line configuration
    WORKERS=${GUNICORN_WORKERS:-4}
    THREADS=${GUNICORN_THREADS:-4}
    WORKER_CLASS=${GUNICORN_WORKER_CLASS:-gthread}
    TIMEOUT=${GUNICORN_TIMEOUT:-120}
    echo "Workers: ${WORKERS}, Threads: ${THREADS}, Worker Class: ${WORKER_CLASS}, Timeout: ${TIMEOUT}s"

    exec gunicorn --bind=0.0.0.0:${PORT:-5000} \
      --workers=${WORKERS} \
      --threads=${THREADS} \
      --worker-class=${WORKER_CLASS} \
      --timeout=${TIMEOUT} \
      --keep-alive=5 \
      --max-requests=1000 \
      --max-requests-jitter=100 \
      --access-logfile='-' \
      --error-logfile='-' \
      --log-level=warning \
      --access-logformat='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"' \
      'run:app'
fi

FROM node:18-alpine AS builder
WORKDIR /app

# Build-time environment variables (can be passed as --build-arg)
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_API_KEY
ARG NEXT_INTERNAL_API_URL
ARG NEXT_PUBLIC_USE_LOCAL_STORE=true
ARG NEXT_PUBLIC_FORCE_API=false
ARG NODE_ENV=production
ARG SYNC_DATA_DURING_BUILD=false

# Set environment variables for build (available during build and runtime)
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_API_KEY=${NEXT_PUBLIC_API_KEY}
ENV NEXT_INTERNAL_API_URL=${NEXT_INTERNAL_API_URL}
ENV NEXT_PUBLIC_USE_LOCAL_STORE=${NEXT_PUBLIC_USE_LOCAL_STORE}
ENV NEXT_PUBLIC_FORCE_API=${NEXT_PUBLIC_FORCE_API}
# DO NOT set NODE_ENV=production here - it will skip devDependencies during npm install

COPY package*.json ./
# Install ALL dependencies including devDependencies (needed for build)
# TailwindCSS, PostCSS, and Autoprefixer are REQUIRED during build for CSS processing
# Explicitly set NODE_ENV to empty during install to ensure devDependencies are installed
RUN NODE_ENV= npm install --no-audit --no-fund && \
    echo "✅ Verifying critical build dependencies..." && \
    echo "Checking if packages exist in node_modules..." && \
    test -d node_modules/tailwindcss && echo "✓ tailwindcss directory exists" || (echo "❌ tailwindcss directory not found!" && echo "Listing node_modules:" && ls node_modules/ | head -20 && exit 1) && \
    test -d node_modules/postcss && echo "✓ postcss directory exists" || (echo "❌ postcss directory not found!" && exit 1) && \
    test -d node_modules/autoprefixer && echo "✓ autoprefixer directory exists" || (echo "❌ autoprefixer directory not found!" && exit 1) && \
    echo "✅ All CSS build dependencies verified and present"

# Now set NODE_ENV for the build process (after dependencies are installed)
ENV NODE_ENV=production

# Copy all files (including styles, configs, etc.)
COPY . .

# Verify critical files and dependencies are present before build
RUN echo "🔍 Verifying build environment..." && \
    echo "Node version:" && node --version && \
    echo "NPM version:" && npm --version && \
    echo "Checking files..." && \
    ls -la styles/globals.css && \
    ls -la postcss.config.js && \
    ls -la tailwind.config.js && \
    ls -la pages/_app.js && \
    ls -la next.config.js && \
    echo "Checking PostCSS/Tailwind..." && \
    npm list postcss tailwindcss autoprefixer 2>/dev/null | head -5 && \
    echo "✅ Build environment verified"

# Create data directory and optionally sync data
# Set SYNC_DATA_DURING_BUILD=true to enable data sync during build
RUN mkdir -p data && \
    if [ "$SYNC_DATA_DURING_BUILD" = "true" ] && [ -n "$NEXT_PUBLIC_API_URL" ] && [ -n "$NEXT_PUBLIC_API_KEY" ]; then \
      echo "🔄 Syncing data from API during build..." && \
      node scripts/sync-data.js 2>&1 || echo "⚠️ Data sync failed, continuing build"; \
    else \
      touch data/.gitkeep && \
      echo "📁 Data directory created (sync skipped - set SYNC_DATA_DURING_BUILD=true to enable)"; \
    fi

# Run the build with increased memory and full output
# Next.js will show detailed errors automatically
RUN echo "🏗️  Starting Next.js build..." && \
    echo "Environment: NODE_ENV=$NODE_ENV" && \
    echo "Memory limit: 4GB" && \
    NODE_OPTIONS="--max-old-space-size=4096" npm run build

# Production runtime image
FROM node:18-alpine AS runner
WORKDIR /app

# Accept build args to pass environment variables to runtime
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_API_KEY
ARG NEXT_INTERNAL_API_URL
ARG NEXT_PUBLIC_USE_LOCAL_STORE=true
ARG NEXT_PUBLIC_FORCE_API=false

# Set environment variables in production image (baked into image)
ENV NODE_ENV=production
ENV PORT=3000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_API_KEY=${NEXT_PUBLIC_API_KEY}
ENV NEXT_INTERNAL_API_URL=${NEXT_INTERNAL_API_URL}
ENV NEXT_PUBLIC_USE_LOCAL_STORE=${NEXT_PUBLIC_USE_LOCAL_STORE}
ENV NEXT_PUBLIC_FORCE_API=${NEXT_PUBLIC_FORCE_API}

# Copy production node_modules and build output
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./next.config.js
# Copy PostCSS and Tailwind config files (needed for runtime CSS processing if any)
COPY --from=builder /app/postcss.config.js ./postcss.config.js
COPY --from=builder /app/tailwind.config.js ./tailwind.config.js
# Copy data directory (may be empty if sync failed, but directory structure is preserved)
COPY --from=builder /app/data ./data
# Copy config.env.example as reference (optional, for documentation)
COPY --from=builder /app/config.env.example ./config.env.example

EXPOSE 3000

CMD ["npm","run","start"]

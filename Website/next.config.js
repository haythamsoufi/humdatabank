/** @type {import('next').NextConfig} */
const path = require('path');

const nextConfig = {
  // Router i18n must be enabled in all environments so router.locale is defined
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'es', 'fr', 'ar', 'hi', 'ru', 'zh'],
    localeDetection: false,
  },

  // Configure images for static export
  images: {
    unoptimized: process.env.NODE_ENV === 'production',
  },

  // Handle trailing slashes
  trailingSlash: true,

  // Ensure Next.js traces files relative to this project folder (not the mono-repo root),
  // avoiding "Cannot find module for page" errors when multiple lockfiles exist.
  outputFileTracingRoot: __dirname,

  // SWC minifier is now the default in Next.js 15 and no longer configurable

  // Development-specific configurations
  ...(process.env.NODE_ENV === 'development' && {
    experimental: {
      workerThreads: false,
    },
    // Allow cross-origin requests in development
    allowedDevOrigins: ['127.0.0.1', 'localhost'],
  }),

  // Production-specific configurations
  ...(process.env.NODE_ENV === 'production' && {
    // Use default server output for SSR on Fly
    // Add build-time optimizations
    experimental: {
      // Reduce concurrent builds to prevent database connection exhaustion
      workerThreads: false,
      // Disable CSS optimization to prevent critters error
      optimizeCss: false,
    },
    // Add build-time environment variables
    env: {
      BUILD_TIME: 'true',
    },
  }),

  // Simplified Webpack configuration
  webpack: (config, { isServer, dev }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
      };

      // Add support for .mjs files (for PDF.js worker)
      config.module.rules.push({
        test: /\.mjs$/,
        type: 'javascript/auto',
      });
    }

    // Simplified development configuration to prevent cache issues
    if (dev) {
      // Disable complex chunk splitting in development
      config.optimization = {
        ...config.optimization,
        splitChunks: {
          chunks: 'async', // Only split async chunks
          cacheGroups: {
            default: {
              minChunks: 2,
              priority: -20,
              reuseExistingChunk: true,
            },
            vendor: {
              test: /[\\/]node_modules[\\/]/,
              name: 'vendors',
              priority: -10,
              chunks: 'async',
            },
          },
        },
      };

      // Add cache configuration with absolute path to prevent corruption
      config.cache = {
        type: 'filesystem',
        buildDependencies: {
          config: [__filename],
        },
        cacheDirectory: path.resolve(__dirname, '.next/cache/webpack'),
      };
    }

    return config;
  },

  // Additional experimental settings if Fast Refresh is disabled
  ...(process.env.DISABLE_FAST_REFRESH === 'true' && {
    experimental: {
      workerThreads: false,
    },
  }),
}

module.exports = nextConfig

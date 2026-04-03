// Minimal service worker for Next.js app
// This prevents 404 errors for service worker requests
// Modified to prevent local network access prompts

self.addEventListener('install', (event) => {
  // Skip waiting to activate immediately
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Take control of all clients immediately
  event.waitUntil(self.clients.claim());
});

// Handle fetch events (minimal implementation)
// Explicitly avoid intercepting requests that might trigger local network access
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Only handle same-origin requests to prevent local network access prompts
  // Don't intercept requests to localhost, 127.0.0.1, or private IP ranges
  if (url.hostname === 'localhost' ||
      url.hostname === '127.0.0.1' ||
      url.hostname.startsWith('192.168.') ||
      url.hostname.startsWith('10.') ||
      /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(url.hostname)) {
    // Let the browser handle these requests normally
    return;
  }

  // For all other requests, just pass through
  // This prevents the service worker from triggering local network permission prompts
});

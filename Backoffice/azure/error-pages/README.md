## Azure App Service custom error pages

These files are **standalone HTML** intended for the Azure Portal setting:

`App Service -> Configuration -> Error pages`

Azure requires:
- ASCII HTML
- Max file size: **10 KB**

Files provided:
- `403.html` (Forbidden)
- `502.html` (Bad Gateway)
- `503.html` (Service Unavailable)

### Features

- **Automatic error logging**: Each page automatically logs error details to `/api/v1/platform-error` endpoint
  - Logs: error code, URL, referrer, user agent, timestamp
  - Secure: URLs sanitized server-side (sensitive params removed)
  - Reliable: Uses `navigator.sendBeacon()` API
  - Silent: Failures don't affect user experience

### Notes

- These pages are for **platform-generated** errors (requests that fail before the Flask app handles them).
- Backoffice already renders custom in-app errors via Flask handlers in `app/__init__.py` using `app/templates/errors/error.html`.
- Error logs are stored in the `SecurityEvent` table via `SecurityMonitor.log_security_event()`.

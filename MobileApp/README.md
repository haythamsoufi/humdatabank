# Humanitarian Databank Mobile App

Generic Flutter mobile application for Humanitarian Databank ecosystems. Point it at your Backoffice URL and organization profile (`assets/config/organization_config.*.json`).

## Features

- **Native Authentication**: Email/password login with Azure AD B2C support
- **Dashboard**: View assignments, entities, and recent activities
- **Notifications**: Real-time notifications with unread counts
- **Settings**: User profile management and preferences
  - Edit name and job title
  - Profile color customization
  - Chatbot preference toggle
- **WebView Integration**: Seamless access to complex backend pages (templates, assignments, forms)
  - URL whitelist validation
  - Content Security Policy enforcement
  - Secure session injection
- **Offline Support**: Comprehensive offline capabilities
  - Request queuing for offline operations
  - Response caching for offline access
  - Automatic sync when connection restored
  - Network status indicators
- **Error Handling**: Centralized error handling with retry logic
- **Performance Monitoring**: Startup time tracking and performance metrics
- **Internationalization**: Multi-language support (English, Spanish, French, Arabic, Hindi, Russian, Chinese)

## Prerequisites

- Flutter SDK (3.0.0 or higher)
- Dart SDK (3.0.0 or higher)
- Android Studio (for Android development)
- Xcode (for iOS development - macOS only)
- CocoaPods (for iOS dependencies)
- Backoffice URL: http://localhost:5000

## Setup Instructions

1. **Clone the repository**
   ```bash
   cd MobileApp
   ```

2. **Install dependencies**
   ```bash
   flutter pub get
   ```

3. **Firebase mobile config** (`google-services.json`, `GoogleService-Info.plist`)

   In [Firebase Console](https://console.firebase.google.com/) → Project settings → Your apps, download the Android and iOS config files and place them at:

   - `android/app/google-services.json`
   - `ios/Runner/GoogleService-Info.plist`

   Those paths are **gitignored** so API keys are not committed. The repo tracks only `android/app/google-services.json.example` and `ios/Runner/GoogleService-Info.plist.example` as templates. CI copies the examples before builds.

   **If keys were ever in a public repository:** rotate and revoke them in [Google Cloud credentials](https://console.cloud.google.com/apis/credentials) / Firebase, then use the new files locally.

4. **Configure environment variables** (optional for local development)
   
   The app supports two methods for providing API keys and configuration:
   
   **Option A: Using `.env` file (for local development)**
   - Create a `.env` file in the `MobileApp` directory (see `.env.example` if available)
   - Add the following variables:
     ```
     MOBILE_APP_API_KEY=your_api_key_here
     SENTRY_DSN=your_sentry_dsn_here  # Optional
     ```
   - The `.env` file is gitignored and will not be committed
   - Note: `.env` is no longer included in Flutter assets to avoid build errors in CI
   
   **Option B: Using `--dart-define` flags (for CI builds and production)**
   - Pass environment variables via command-line flags:
     ```bash
     flutter run --dart-define=MOBILE_APP_API_KEY=your_key
     ```
   - For CI builds, these are passed automatically from GitHub secrets
   
   **Priority order:**
   1. `.env` file (if available and loaded successfully)
   2. `--dart-define` flags
   3. Empty string (default)

   **API version header:** Every request to the backoffice includes `X-App-Version` (semver from the app package). When the server sets `MOBILE_MIN_APP_VERSION`, clients at or below the minimum receive HTTP 426 with `error_code: APP_UPDATE_REQUIRED` (only applies to requests that send this header).

5. **Add IFRC logo asset**
   - Place `ifrc_logo.png` in `assets/images/` directory
   - Or update the asset path in `lib/screens/login_screen.dart`

6. **iOS Setup** (macOS only)
   ```bash
   cd ios
   pod install
   cd ..
   ```
   See `docs/ios/setup.md` for detailed iOS setup instructions.

7. **Run the app**

   **For development (localhost):**
   ```bash
   flutter run
   ```
   **For staging (IFRC staging backoffice — `databank-stage.ifrc.org`):**
   ```bash
   flutter run --dart-define=STAGING=true
   ```

   **For production (IFRC backoffice `databank.ifrc.org` + public site on Fly.io) in emulator:**
   ```bash
   flutter run --dart-define=PRODUCTION=true
   ```

   **For production on a specific device:**
   ```bash
   flutter run --dart-define=PRODUCTION=true -d <device-id>
   ```

   **For staging on a specific device:**
   ```bash
   flutter run --dart-define=STAGING=true -d <device-id>
   ```
   
   To list available devices:
   ```bash
   flutter devices
   ```

## Project Structure

```
lib/
├── config/          # App configuration and routes
│   ├── app_config.dart      # Environment config, API endpoints
│   └── routes.dart          # Route definitions
├── models/          # Data models (User, Assignment, etc.)
│   ├── shared/      # Shared models
│   ├── admin/       # Admin-specific models
│   └── indicator_bank/  # Indicator bank models
├── services/        # API and storage services
│   ├── api_service.dart          # HTTP client with retry & interceptors
│   ├── auth_service.dart         # Authentication
│   ├── user_profile_service.dart # User profile management
│   ├── session_service.dart      # Session management
│   ├── offline_queue_service.dart # Request queuing
│   ├── offline_cache_service.dart # Response caching
│   ├── connectivity_service.dart  # Network monitoring
│   ├── error_handler.dart         # Centralized error handling
│   ├── webview_service.dart       # WebView configuration
│   └── performance_service.dart   # Performance monitoring
├── providers/       # State management providers
│   ├── shared/      # Core providers (always loaded)
│   ├── admin/       # Admin providers (loaded on-demand)
│   └── public/      # Public-facing providers
├── screens/         # UI screens
│   ├── public/      # Public screens
│   ├── shared/      # Shared screens (login, dashboard, settings)
│   └── admin/       # Admin screens
├── widgets/         # Reusable widgets
│   ├── offline_indicator.dart    # Network status indicator
│   ├── error_boundary.dart       # Error handling wrapper
│   └── ...
├── utils/           # Utilities and constants
│   ├── debug_logger.dart   # Logging utility
│   ├── theme.dart          # Theme configuration
│   └── constants.dart      # App constants
└── l10n/            # Localization
    └── app_localizations.dart  # Translation strings
```

See the [Documentation](#documentation) section below for architecture and setup guides.

## Authentication

The app supports two authentication methods:

1. **Email/password**: Native authentication against Backoffice
2. **Azure AD B2C**: Single sign-on with your organization’s identity provider (when configured)

Quick test logins are available for development:
- Admin: `test_admin@humdatabank.org` / `test123`
- Focal Point: `test_focal@humdatabank.org` / `test123`

## WebView Integration

Complex backend pages are accessed via authenticated WebView:
- Template Management
- Assignment Management
- Form Builder
- Form Data Entry
- Admin Pages

Session cookies are automatically injected to maintain authentication.

## Offline Support

The app implements comprehensive offline support:

### Request Queuing
- Failed requests are automatically queued when offline
- Queued requests sync when connection is restored
- Maximum 3 retries with exponential backoff
- Visual indicator shows queued request count

### Response Caching
- GET requests are cached for offline access
- Default TTL: 1 hour (configurable)
- Cache stored in SQLite database
- Automatic cache invalidation

### Network Monitoring
- Real-time network status detection
- Automatic sync when connection restored
- Manual sync option available
- "Last synced" timestamp tracking

### Cached Data
- Dashboard data (1 hour expiration)
- User profile
- Entity list
- API responses (configurable TTL)

Cache is automatically refreshed on pull-to-refresh or app resume.

## Organization Configuration

The app supports organization-specific branding and configuration through JSON files. See `assets/config/README.md` for details.

Example:

```bash
# Build with a named organization profile (example: ifrc)
flutter build appbundle --release --dart-define=ORGANIZATION_CONFIG=ifrc --dart-define=PRODUCTION=true

# Build with default Humanitarian Databank configuration
flutter build appbundle --release --dart-define=PRODUCTION=true
```

## Building for Production

### Environment Configuration

The app supports three environments:
- **Staging**: Uses your configured staging Backoffice URL (see `assets/config/`). (For the IFRC staging profile this is `https://databank-stage.ifrc.org`.)
- **Production**: Backoffice/API traffic goes to **IFRC** (`https://databank.ifrc.org`). The public website used in-app is **`https://website-databank.fly.dev`** (Fly.io). Do not confuse IFRC production with `https://backoffice-databank.fly.dev` (a separate Fly-hosted preview).

### Android - Production APK

To build a production APK that uses the production host defaults above:

```bash
flutter build apk --release --dart-define=PRODUCTION=true
```
To build a staging APK that connects to your staging Backoffice:
To build a staging APK that connects to databank-stage.ifrc.org:

```bash
flutter build apk --release --dart-define=STAGING=true
```

The APK will be generated at: `build/app/outputs/flutter-apk/app-release.apk`

**For development/testing with localhost:**
```bash
flutter build apk --release
# or for debug builds
flutter build apk --debug
```

**For App Bundle (Google Play Store):**
```bash
flutter build appbundle --release --dart-define=PRODUCTION=true
```

**For Staging App Bundle:**
```bash
flutter build appbundle --release --dart-define=STAGING=true
```

### iOS - Production Build

```bash
flutter build ios --release --dart-define=PRODUCTION=true
```

**For Staging Build:**
```bash
flutter build ios --release --dart-define=STAGING=true
```

**Note**: iOS builds require:
- macOS with Xcode installed
- Valid Apple Developer account for device testing
- CocoaPods dependencies installed (`cd ios && pod install`)
- See `ios/SETUP_IOS.md` for complete iOS setup guide

### Verifying Environment Configuration

After building with `--dart-define=PRODUCTION=true`, the app will:
- Call the Backoffice/API at **`https://databank.ifrc.org`** (unless overridden with `BACKEND_URL`)
- Load public website pages from **`https://website-databank.fly.dev`**
- Use HTTPS for all network requests

After building with `--dart-define=STAGING=true`, the app will:
- Connect to your configured staging Backoffice base URL (or `https://databank-stage.ifrc.org` when using the IFRC staging profile)
- Load website pages from `https://website-databank.fly.dev`
- Use HTTPS for all network requests

## Security Features

### WebView Security
- **URL Whitelist**: Only approved URLs can be loaded
- **Content Security Policy**: Injected to prevent XSS attacks
- **URL Validation**: All navigation validated before loading
- **Session Security**: Secure cookie storage and automatic refresh

### Authentication Security
- Session-based authentication with secure cookie storage
- Client-side session expiration validation
- Automatic session refresh before expiration
- Secure session rotation on cookie updates

### Data Security
- Sensitive data masking in logs
- Encrypted storage for credentials
- HTTPS-only in production environment
- Error tracking integration (Sentry - optional)

## API Service Features

### Request Interceptors
- Modify headers before requests
- Add custom headers dynamically
- Logging and monitoring

### Response Interceptors
- Process responses after requests
- Response logging
- Custom response handling

### Automatic Retry
- Retries transient failures (502, 503, 504, timeouts)
- Exponential backoff strategy
- Configurable retry count and delays
- Smart retry logic (no retry for 401, 400 errors)

## Troubleshooting

### Session Issues
If you experience authentication issues:
1. Logout and login again
2. Clear app data/cache
3. Check backend connectivity
4. Verify session expiration (should auto-refresh)

### WebView Not Loading
- Ensure backend URL is correct
- Check network connectivity
- Verify session cookie is valid
- Check URL whitelist (should match backend URL)

### Offline Issues
- Check network connectivity indicator
- Verify queued requests count
- Try manual sync
- Check cache expiration

### Build Issues
- Run `flutter clean` and `flutter pub get`
- Verify Flutter SDK version (>=3.0.0 <4.0.0)
- Check dependency versions in `pubspec.yaml`
- For iOS: Run `pod install` in `ios/` directory

## Documentation

All documentation is organized under `docs/`.

- **Docs index**: **[`docs/README.md`](docs/README.md)**
- **Organization config JSON reference**: [`assets/config/README.md`](assets/config/README.md)

## Privacy Policy
The Humanitarian Databank mobile app collects and processes user data as described in your deployment’s Privacy Policy.

**Privacy Policy URL:** https://website-databank.fly.dev/privacy-policy

This URL is required when submitting the app to:
- Google Play Store
- Apple App Store

For detailed information about data collection, usage, and user rights, please visit the Privacy Policy page or see [PRIVACY_POLICY.md](PRIVACY_POLICY.md).

## Architecture notes (routing, HTTP, shared UI)

- **Navigation**: The app uses **Navigator 1.0** with [`MaterialApp.routes`](lib/main.dart) / [`AppRouter`](lib/config/app_router.dart) and [`AppRoutes`](lib/config/routes.dart). A **go_router** configuration exists in [`go_router_config.dart`](lib/config/go_router_config.dart) for a future migration; **do not register the same path in both** until the app is switched to `MaterialApp.router`.
- **Dependency injection**: Shared services are registered in [`setupServiceLocator()`](lib/di/service_locator.dart) (GetIt). Prefer **`sl<ApiService>()`** (and other `sl<T>()`) over calling `ApiService()` directly so tests can override registrations.
- **Mobile API JSON**: Helpers for `success`/`data` envelopes live in [`lib/utils/mobile_api_json.dart`](lib/utils/mobile_api_json.dart).
- **Async UI**: [`AppLoadingIndicator`](lib/widgets/loading_indicator.dart), [`AppErrorState`](lib/widgets/error_state.dart), [`AsyncBody`](lib/widgets/async/async_body.dart), and optional [`MobileScreenScaffold`](lib/widgets/mobile_screen_scaffold.dart) for pushed routes.
- **Provider async helper**: [`AsyncOperationMixin`](lib/providers/shared/async_operation_mixin.dart) is used by [`LeaderboardProvider`](lib/providers/public/leaderboard_provider.dart) and [`ManageUsersProvider.loadUsers`](lib/providers/admin/manage_users_provider.dart).

## License

**Proprietary — see repository LICENSE**

This mobile app component is part of the Humanitarian Databank ecosystem. Licensing and authorized use are defined in [LICENSE](../../LICENSE); do not use or distribute outside the terms that apply to your deployment.
This mobile app component is part of the IFRC Network Databank ecosystem, which is proprietary software developed by Haytham ALSOUFI as an individual and is licensed for use by the International Federation of Red Cross and Red Crescent Societies (IFRC) Secretariat and its network of National Societies. Use is restricted to the IFRC network only. See [LICENSE](../../LICENSE) for complete license terms.

For licensing inquiries, permissions, or questions about authorized use, please contact:
Haytham ALSOUFI: haythamsoufi@outlook.com

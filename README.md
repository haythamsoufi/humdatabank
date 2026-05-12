## Humanitarian Databank ✨

A modern, multilingual, full‑stack ecosystem for humanitarian data management, analytics, and public reporting.

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-Backoffice-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-DB-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Node.js](https://img.shields.io/badge/Node.js-18+-339933?logo=nodedotjs&logoColor=white)](https://nodejs.org/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![Flutter](https://img.shields.io/badge/Flutter-3.0+-02569B?logo=flutter&logoColor=white)](https://flutter.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-UI-38B2AC?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![i18next](https://img.shields.io/badge/i18next-multilingual-26A69A)](https://www.i18next.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red)](LICENSE)
[![iOS Build](https://img.shields.io/github/actions/workflow/status/haythamsoufi/humdatabank/ios-build.yml?label=iOS%20Build&logo=apple&logoColor=white)](https://github.com/haythamsoufi/humdatabank/actions/workflows/ios-build.yml)
[![Android Build](https://img.shields.io/github/actions/workflow/status/haythamsoufi/humdatabank/android-build.yml?label=Android%20Build&logo=android&logoColor=white)](https://github.com/haythamsoufi/humdatabank/actions/workflows/android-build.yml)

**Complete Ecosystem**: This repository includes the full ecosystem of applications:
- 🖥️ **Backoffice/Admin Panel**: Flask-based backend with comprehensive admin interface for data management
- 🌐 **Website**: Next.js public-facing website for data visualization and reporting
- 📱 **Mobile App**: Native Flutter application for iOS and Android with offline support

Together, these components form a complete data ecosystem and data management solution for humanitarian organizations.

Test on:
https://backoffice-databank.fly.dev/
https://website-databank.fly.dev/

> 🚀 **POWERED BY VIBE CODING** 🚀
> 
> This project proudly embraces **vibe coding** — a modern development philosophy that prioritizes rapid iteration, AI-assisted development, and pragmatic problem-solving. Approximately **90% of this codebase** was built using this approach, and it's **production-ready, battle-tested, and fully functional**.
> 
> **Why vibe coding works:**
> - ⚡ **Speed**: Rapid development cycles that deliver working solutions fast
> - 🤖 **AI-Assisted**: Leveraging cutting-edge AI tools for intelligent code generation
> - 🎯 **Pragmatic**: Focus on what works, not just what's conventional
> - 🔄 **Iterative**: Continuous improvement through real-world testing
> - 💪 **Production-Ready**: This isn't a prototype — it's a fully deployed, working system
> 
> **What you'll find:**
> - Code that solves real problems efficiently
> - Patterns that prioritize functionality and maintainability
> - A codebase that proves modern development approaches work at scale
> - Documentation that reflects the actual development journey
> 
> **Join the vibe coding movement** — where pragmatism meets innovation, and results speak louder than conventions. 🎨✨

### Why you'll love it

- 🌍 Multilingual by design (English, French, Spanish, Arabic, Chinese, Russian, Hindi)
- 📊 Rich analytics: disaggregation analysis, dynamic indicators, indicator bank
- 🧭 Beautiful, responsive Next.js frontend with Tailwind and Leaflet maps
- 📱 Native Flutter mobile app for iOS and Android with offline support
- ⚙️ Solid Flask backend with clear docs, scripts, and migration workflow
- 🔐 Azure AD authentication support for enterprise SSO
- 🔌 Translation service integration via LibreTranslate
- 🧩 Modular architecture and comprehensive documentation

### Monorepo structure

```text
Humanitarian Databank/
├─ Backoffice/
│  ├─ docs/                 # Documentation (API, features, setup, migration, translation, indicators)
│  ├─ config/               # Configuration files and setup scripts
│  ├─ docker/               # Docker Compose and related config
│  ├─ scripts/              # Utility and maintenance scripts
│  ├─ tools/                # Dev/debug tools
│  ├─ app/                  # Flask application
│  ├─ migrations/           # Database migrations
│  ├─ instance/             # Instance-specific data
│  ├─ (optional) LibreTranslate data via Docker volume
│  └─ uploads/              # File uploads
├─ Website/
│  ├─ pages/                # Next.js pages (router)
│  ├─ components/           # UI components
│  ├─ lib/                  # API utilities & helpers
│  ├─ public/               # Static assets & locales
│  ├─ styles/               # Tailwind and global CSS
│  └─ scripts/              # Dev utilities
└─ MobileApp/
   ├─ lib/                  # Flutter application code
   │  ├─ config/            # App configuration and routes
   │  ├─ models/            # Data models
   │  ├─ services/          # API and storage services
   │  ├─ providers/         # State management providers
   │  ├─ screens/           # UI screens
   │  ├─ widgets/           # Reusable widgets
   │  └─ utils/             # Utilities and constants
   ├─ android/              # Android-specific configuration
   ├─ ios/                  # iOS-specific configuration
   └─ assets/               # Images, fonts, and other assets
```

## Quick links

- Backoffice docs index: `Backoffice/docs/README.md`
- Setup & configuration: `Backoffice/docs/setup/`
- API docs: `Backoffice/docs/api/`
- Features: `Backoffice/docs/features/`
- Indicators & analytics: `Backoffice/docs/indicators/`
- Data migration: `Backoffice/docs/data-migration/`
- Translation & localization: `Backoffice/docs/translation/`
- Mobile app: `MobileApp/README.md`

## Architecture

```mermaid
graph LR
    %% User Interface Layer
    subgraph "🌐 User Interface Layer"
        subgraph "Web Website"
            A[Next.js 15 / React 18]
            A1[Tailwind CSS]
            A2[i18next]
            A3[Leaflet Maps]
            A4[PDF Generation]
        end
        subgraph "Mobile App"
            A5[Flutter 3.0+]
            A6[Native iOS/Android]
            A7[Offline Support]
            A8[Push Notifications]
        end
    end

    %% API Gateway Layer
    subgraph "🔌 API Gateway Layer"
        subgraph "Backoffice Services"
            B[Flask REST API]
            B1[Authentication]
            B2[Rate Limiting]
            B3[CSRF Protection]
            B4[Request Validation]
        end
    end

    %% Data Storage Layer
    subgraph "💾 Data Storage Layer"
        subgraph "Primary Database"
            C[(PostgreSQL)]
            C1[User Management]
            C2[Form Templates]
            C3[Analytics Data]
            C4[Multilingual Content]
        end
        
        subgraph "Cache Layer"
            D1[Session Storage]
            D2[API Cache]
            D3[Translation Cache]
        end
    end

    %% External Services Layer
    subgraph "🌍 External Services Layer"
        subgraph "Translation Service"
            E[LibreTranslate]
            E1[Auto-translation]
            E2[Human Review]
        end
        
        subgraph "Communication"
            F[Email Service]
            F1[User Notifications]
            F2[System Alerts]
        end
    end

    %% File Management Layer
    subgraph "📁 File Management Layer"
        subgraph "Storage System"
            G[Local Storage]
            G1[Documents]
            G2[Reports]
            G3[Static Assets]
        end
    end

    %% Data Flow Connections
    A -->|REST API| B
    A -->|Static Assets| G
    A5 -->|REST API| B
    B -->|ORM Queries| C
    B -->|Cache Ops| D
    B -->|Translation| E
    B -->|Email| F
    B -->|File Ops| G
    
    %% Internal Layer Connections
    A1 -.->|Styling| A
    A2 -.->|Localization| A
    A3 -.->|Maps| A
    A4 -.->|Reports| A
    A6 -.->|Native UI| A5
    A7 -.->|Caching| A5
    A8 -.->|Firebase| A5
    
    B1 -.->|Security| B
    B2 -.->|Performance| B
    B3 -.->|Protection| B
    B4 -.->|Validation| B
    
    C1 -.->|Users| C
    C2 -.->|Forms| C
    C3 -.->|Analytics| C
    C4 -.->|Translations| C
    
    D1 -.->|Sessions| D
    D2 -.->|API Cache| D
    D3 -.->|Translation Cache| D
    
    E1 -.->|Auto-translate| E
    E2 -.->|Manual Review| E
    
    F1 -.->|User Emails| F
    F2 -.->|System Emails| F
    
    G1 -.->|Documents| G
    G2 -.->|Reports| G
    G3 -.->|Assets| G

    %% Styling
    classDef frontend fill:#61dafb,stroke:#333,stroke-width:2px,color:#000
    classDef backend fill:#ff6b6b,stroke:#333,stroke-width:2px,color:#fff
    classDef database fill:#4ecdc4,stroke:#333,stroke-width:2px,color:#000
    classDef service fill:#45b7d1,stroke:#333,stroke-width:2px,color:#fff
    classDef storage fill:#96ceb4,stroke:#333,stroke-width:2px,color:#000
    
    class A,A1,A2,A3,A4,A5,A6,A7,A8 frontend
    class B,B1,B2,B3,B4 backend
    class C,C1,C2,C3,C4,D,D1,D2,D3 database
    class E,E1,E2,F,F1,F2 service
    class G,G1,G2,G3 storage
```

### Ecosystem Components

**Web Website (Next.js 15)**
- **React 18** with modern hooks and concurrent features
- **Tailwind CSS** for responsive, utility-first styling
- **i18next** for comprehensive multilingual support (7 languages)
- **Leaflet** for interactive maps and data visualization
- **PDF generation** with jsPDF for report exports

**Mobile App (Flutter 3.0+)**
- **Native iOS and Android** applications
- **Provider** for state management
- **Offline caching** for dashboard and user data
- **Firebase Cloud Messaging** for push notifications
- **WebView integration** for complex backend pages
- **Multilingual support** with RTL support for Arabic (Tajawal font)
- **Secure storage** for authentication tokens

**Backoffice (Flask)**
- **RESTful API** with comprehensive CRUD operations
- **SQLAlchemy ORM** for database abstraction and migrations
- **Authentication system** with role-based access control and Azure AD integration
- **Rate limiting** and request validation
- **CSRF protection** and security middleware

**Data Layer**
- **PostgreSQL** as primary database with advanced indexing
- **Alembic** for database migrations and version control

**External Integrations**
- **Azure AD** for enterprise authentication and SSO
- **LibreTranslate** for automated and human-reviewed translations
- **SMTP services** for email notifications and alerts
- **File upload** and document management system

**Key Features**
- **Multilingual support** across 7 languages with RTL support
- **Dynamic form builder** with conditional logic and calculated fields
- **Advanced analytics** with disaggregation analysis and indicator bank
- **Real-time data visualization** with interactive charts and maps
- **Comprehensive admin panel** with user management and analytics
- **Native mobile apps** for iOS and Android with offline support
- **Push notifications** for real-time updates and alerts

## Quick start

### Option 1: Docker Setup (Recommended)

The fastest way to get started is using Docker Compose:

```bash
# 1. Clone the repository
git clone <repository-url>
cd "Humanitarian Databank"

# 2. Start all services with automatic database initialization
docker-compose up -d

# 3. Verify everything is running
docker-compose ps

# 4. Access the application
# Backoffice API: http://localhost:5000
# Health check: http://localhost:5000/health
```

The Docker setup automatically:
- Creates and initializes the PostgreSQL database
- Runs all database migrations
- Creates default test data (users and countries)
- Starts the Flask backend
- LibreTranslate service is optional (see `Backoffice/README.md` for setup)

See the [Docker Setup section](#docker-setup-recommended) for detailed instructions.

### Option 2: Manual Setup

### Prerequisites

- Python 3.8+
- Node.js 18+ and npm
- PostgreSQL (must be installed and running)
- Optional: LibreTranslate (for translations - see `Backoffice/README.md` for setup)
- Optional: Flutter 3.0+ (for mobile app development)

### 1) Backoffice (Flask)

```bash
cd Backoffice

pip install -r requirements.txt

# Environment — copy the quickstart example and you're ready to go
# Windows (PowerShell)
Copy-Item env.quickstart.example .env
# macOS/Linux
cp env.quickstart.example .env

# Database setup (REQUIRED)
# Make sure PostgreSQL is running and create the database:
# psql -U postgres -c "CREATE DATABASE hum_databank;"
# psql -U postgres -c "CREATE USER app WITH PASSWORD 'app';"
# psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE hum_databank TO app;"

# Run database migrations
# Windows: $env:FLASK_APP = "run.py"
flask db upgrade

# Seed RBAC roles
flask rbac seed

# Seed test users (creates System Manager, Admin, and Focal Point)
flask seed-test-data

# Run dev server (default http://127.0.0.1:5000)
python run.py
```

After starting the server, open http://127.0.0.1:5000 and use the quick-login buttons to sign in as System Manager, Admin, or Focal Point (no typing required).

Default test credentials (set in `.env` via `env.quickstart.example`):
- **System Manager**: `test_sys@humdatabank.org` / `test123`
- **Admin**: `test_admin@humdatabank.org` / `test123`
- **Focal Point**: `test_focal@humdatabank.org` / `test123`

Helpful npm scripts in `Backoffice/package.json` (for CSS):

```bash
npm run watch:css   # watch Tailwind CSS
npm run build:css   # build Tailwind CSS
```

### 2) Website (Next.js)

```bash
cd Website
npm install

# Website needs the backend URL
# Create .env.local and set:
# For Docker setup:
# NEXT_PUBLIC_API_URL=http://localhost:5000
# For manual setup:
# NEXT_PUBLIC_API_URL=http://127.0.0.1:5000

npm run dev        # http://localhost:3000
# or choose another port: npm run dev -- -p 3001
```

Key scripts in `Website/package.json`:

```bash
npm run dev         # start dev server (copies PDF worker automatically)
npm run build       # production build
npm run start       # start built app
npm run lint        # lint
npm run dev:reset   # clear cache, reinstall, and restart dev
```

### 3) Mobile App (Flutter)

```bash
cd MobileApp

# Install dependencies
flutter pub get

# Configure backend URL (if needed)
# Edit lib/config/app_config.dart and update backendUrl

# Run on connected device or emulator
flutter run

# For iOS (macOS only)
cd ios
pod install
cd ..
flutter run
```

**Prerequisites for Mobile App:**
- Flutter SDK 3.0.0 or higher
- Dart SDK 3.0.0 or higher
- Android Studio (for Android development)
- Xcode (for iOS development - macOS only)
- CocoaPods (for iOS dependencies)

**Key Features:**
- Native authentication with email/password and Azure AD SSO
- Dashboard with assignments and entities
- Real-time notifications
- WebView integration for complex backend pages
- Offline caching support
- Push notifications via Firebase

See `MobileApp/README.md` for detailed mobile app setup instructions.

## Environment & configuration

- Backoffice
  - Configure env via `.env` and files in `Backoffice/config/`
  - Database: `POSTGRES_*` and SQLAlchemy URI
  - Email, logging, and translation setup docs live under `Backoffice/docs/`
- Website
  - `NEXT_PUBLIC_API_URL`: base URL of the backend API (defaults to `http://127.0.0.1:5000` if unset)
  - Optional: `DISABLE_FAST_REFRESH=true` for certain dev scenarios
- Mobile App
  - Backoffice URL configured in `lib/config/app_config.dart` (defaults to `http://localhost:5000`)
  - Firebase configuration required for push notifications (see `MobileApp/README.md`)

See `Backoffice/docs/setup/` and `Backoffice/config/README.md` for detailed guidance.

### Example env files

Backoffice `.env` (example):

```bash
FLASK_ENV=development
SECRET_KEY=change-me
SQLALCHEMY_DATABASE_URI=postgresql://app:app@127.0.0.1:5432/databank
# Optional integrations
LIBRETRANSLATE_URL=http://127.0.0.1:5001
```

Website `.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:5000
DISABLE_FAST_REFRESH=true
```

## Docker Setup (Recommended)

The easiest way to get started is using Docker Compose, which sets up the complete stack with automatic database initialization.

### Quick Start with Docker

```bash
# Clone and navigate to the project
cd "Humanitarian Databank"

# Start all services (database, migrations, backoffice, translation service)
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f backoffice

# Rebuild and start with clean logs
docker-compose build --no-cache backoffice
```

### What Docker Compose Sets Up

Default Postgres database and container names are generic (`hum_databank`, `hum-databank-postgres`). Override `POSTGRES_DB` in compose or your `.env` if you must keep a legacy database name (e.g. after an existing volume migration).

The `docker-compose.yml` includes:

1. **PostgreSQL Database** (`hum-databank-postgres`)
   - Port: 5432
   - Database: `hum_databank` (override with `POSTGRES_DB`)
   - User: `app` / Password: `app`
   - Persistent data storage

2. **Flask Backoffice** (`databank-backoffice`)
   - Port: 5000
   - Runs database migrations, seeds RBAC roles, and creates test users on first startup
   - Depends on healthy database

### First-Time Setup

```bash
# 1. Start the services
docker-compose up -d

# 2. Verify backoffice is running (check logs)
docker-compose logs backoffice

# 4. Access the application
# Backoffice API: http://localhost:5000
# Health check: http://localhost:5000/health
```

### Default Data Created

On first startup, the ecosystem automatically creates:

- **Test Country**: "Testland" (TST) in Europe region
- **System Manager User**: `test_sys@humdatabank.org` (password: `test123`)
- **Admin User**: `test_admin@humdatabank.org` (password: `test123`)
- **Focal Point User**: `test_focal@humdatabank.org` (password: `test123`)

Quick-login buttons appear on the login page in development mode when `TEST_ADMIN_PASSWORD`, `TEST_FOCAL_PASSWORD`, and `TEST_SYS_MANAGER_PASSWORD` are set (Docker Compose sets these to `test123` by default).

**Note**: The default users are created with test password hashes. For production use, you should change the passwords after first login.

### Environment Variables

Create a `.env` file in the Backoffice directory to customize:

```bash
# Database
POSTGRES_USER=app
POSTGRES_PASSWORD=app
POSTGRES_DB=hum_databank

# Flask
FLASK_CONFIG=production
SECRET_KEY=your-secret-key-here
```

### Troubleshooting

```bash
# Check service status
docker-compose ps

# View specific service logs
docker-compose logs backoffice

# Restart a service
docker-compose restart backoffice

# Rebuild and restart everything
docker-compose down
docker-compose up -d --build

# Reset database (WARNING: deletes all data)
docker-compose down -v
docker-compose up -d
```

### Manual Database Operations

```bash
# Run database migrations manually
docker-compose exec backoffice flask db upgrade

# Check migration status
docker-compose exec backoffice flask db current

# Access database directly
docker-compose exec db psql -U app -d hum_databank
```

## API overview

Base URL: `http://localhost:5000` (Docker) or `http://127.0.0.1:5000` (Manual setup)

- `GET /api/v1/data?api_key=...&template_id=2&per_page=...&period_name=...&indicator_bank_id=...`
- `GET /api/v1/resources?api_key=...&page=...&per_page=...&search=...&resource_type=...&language=...`
- `GET /api/v1/countrymap?api_key=...`
- `GET /api/v1/indicator-bank?api_key=...&search=...&type=...&sector=...&sub_sector=...&emergency=...&archived=...`
- `GET /api/v1/sectors-subsectors?api_key=...`

## Mobile App (Flutter)

The Humanitarian Databank mobile app provides native iOS and Android access to the ecosystem with comprehensive offline support, real-time notifications, and seamless integration with the backend.

### Key Features

**Authentication & Security**
- **Email/Password Login**: Standard credential-based authentication
- **Azure AD B2C SSO**: Enterprise single sign-on support (coming soon)
- **Session Management**: Secure cookie storage with automatic session refresh
- **Encrypted Storage**: Sensitive data stored securely using Flutter Secure Storage

**Core Functionality**
- **Dashboard**: View assignments, entities, and recent activities
- **Real-time Notifications**: Push notifications via Firebase Cloud Messaging with unread counts
- **User Profile**: Edit name, job title, and customize profile colors
- **Settings**: Manage preferences including chatbot toggle

**WebView Integration**
- **Seamless Backoffice Access**: Complex backend pages accessible via authenticated WebView
  - Template Management
  - Assignment Management
  - Form Builder
  - Form Data Entry
  - Admin Pages
- **Security Features**:
  - URL whitelist validation
  - Content Security Policy enforcement
  - Secure session cookie injection

**Offline Support**
- **Request Queuing**: Failed requests automatically queued when offline
- **Response Caching**: GET requests cached in SQLite for offline access (1-hour default TTL)
- **Automatic Sync**: Queued requests sync when connection is restored
- **Network Monitoring**: Real-time connectivity status with visual indicators
- **Cached Data**: Dashboard, user profile, entity list, and API responses

**Performance & Reliability**
- **Automatic Retry**: Transient failures retried with exponential backoff (max 3 retries)
- **Error Handling**: Centralized error handling with retry logic
- **Performance Monitoring**: Startup time tracking and performance metrics
- **Request/Response Interceptors**: Custom headers, logging, and monitoring

**Internationalization**
- **Multi-language Support**: English, Spanish, French, Arabic, Hindi, Russian, Chinese
- **RTL Support**: Full right-to-left support for Arabic with Tajawal font
- **Localization**: Flutter's localization system with custom AppLocalizations

### Architecture

The mobile app follows a modular architecture:

```
lib/
├── config/          # App configuration and routes
├── models/          # Data models (User, Assignment, etc.)
├── services/        # API, auth, storage, offline services
├── providers/       # State management (Provider pattern)
├── screens/         # UI screens (public, shared, admin)
├── widgets/         # Reusable widgets
├── utils/           # Utilities and constants
└── l10n/            # Localization strings
```

**State Management**: Provider pattern with lazy-loaded admin providers
**Storage**: SQLite for offline cache, Secure Storage for credentials
**HTTP Client**: Custom service with retry logic and interceptors
**Connectivity**: Real-time network monitoring with automatic sync

### Building for Production

**Android:**
```bash
# Production APK (connects to fly.dev)
flutter build apk --release --dart-define=PRODUCTION=true

# App Bundle (Google Play Store)
flutter build appbundle --release --dart-define=PRODUCTION=true
```

**iOS:**
```bash
flutter build ios --release --dart-define=PRODUCTION=true
```

**Environment Configuration:**
- **Development** (default): `http://localhost:5000` (backend), `http://localhost:3000` (frontend)
- **Production**: `https://backoffice-databank.fly.dev` (backoffice), `https://website-databank.fly.dev` (website)

### Development

**Quick Start:**
```bash
cd MobileApp
flutter pub get

# iOS setup (macOS only)
cd ios && pod install && cd ..

# Run app
flutter run                                    # Development (localhost)
flutter run --dart-define=PRODUCTION=true      # Production (fly.dev)
```

**Test Credentials:**
- System Manager: `test_sys@humdatabank.org` / `test123`
- Admin: `test_admin@humdatabank.org` / `test123`
- Focal Point: `test_focal@humdatabank.org` / `test123`

For detailed setup instructions, architecture documentation, and troubleshooting, see [`MobileApp/README.md`](MobileApp/README.md).

## Internationalization & UX

- **Web Website**: Uses i18next and Next.js i18n for multiple locales.
- **Mobile App**: Uses Flutter's localization system with custom AppLocalizations.
- **Arabic Support**: For Arabic content, use the Tajawal font in both web and mobile UIs.
- **Translation Services**: Integrate with LibreTranslate. Do not use mock translation responses; surface errors to the user if translation APIs fail.
- **RTL Support**: Available for Arabic in both web and mobile; ensure components respect direction and typography.

## Contributing

We welcome contributions that embrace the **vibe coding philosophy** — rapid iteration, pragmatic solutions, and AI-assisted development are all encouraged!

For branching, pull requests, branch protection (GitHub / `gh`), and collaboration conventions, see **[CONTRIBUTING.md](CONTRIBUTING.md)**. For security reports see **[SECURITY.md](SECURITY.md)**.

- Follow the established structure and update docs when adding features.
- Test thoroughly before submitting changes.
- Use the migration procedures for database changes.
- **Vibe coding is welcome**: Don't overthink it — if it works and solves the problem, that's what matters!

### Development tips

- If Fast Refresh misbehaves, try `npm run dev:reset` in `Website/` (see `Website/TROUBLESHOOTING.md`).
- Clear Next.js cache by removing `.next/` if needed.
- For large data views, prefer server-side filtering when available.
- **Embrace rapid iteration**: Try things, test them, iterate. That's the vibe coding way! 🚀

## License

**Proprietary**

This ecosystem (backoffice, website, and mobile app components) is proprietary software. Authorized use, redistribution, and modification are defined in [LICENSE](LICENSE) and any separate agreements with the copyright holder.

**Unauthorized use, copying, modification, distribution, or disclosure may be prohibited.**

See [LICENSE](LICENSE) for complete license terms and restrictions.

For licensing inquiries, permissions, or questions about authorized use, please contact:
Haytham ALSOUFI: haythamsoufi@outlook.com

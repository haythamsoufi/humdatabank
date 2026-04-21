# Humanitarian Databank Backoffice

This is the backoffice/admin component of the Humanitarian Databank ecosystem, a comprehensive data management and analytics platform for humanitarian organizations.

## 📁 Project Structure

```
Backoffice/
├── 📚 docs/                    # Documentation (see docs/README.md for index)
│   ├── getting-started/       # Getting started and glossary
│   ├── user-guides/           # Guides by role (admin, focal point, common)
│   ├── workflows/             # Workflow documentation
│   └── ...                    # Engineering runbooks, diagrams, etc.
├── ⚙️ config/                 # Configuration (e.g. config.py)
├── 🔧 scripts/                # Utility and maintenance scripts
├── 🛠️ tools/                  # Development and debugging tools
├── 📱 app/                    # Main Flask application
├── 🗄️ migrations/             # Database migrations (Flask-Migrate)
├── 📊 instance/               # Instance-specific data (e.g. uploads, logs)
├── 🌍 (optional) LibreTranslate data via Docker volume
└── 📁 uploads/                # File uploads (or under instance/)
```

## 🚀 Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   - Copy `env.quickstart.example` to `.env` (minimal local defaults), or `env.example` for the full reference
   - Set `DATABASE_URL` to a PostgreSQL connection string (e.g. `postgresql+psycopg2://app:app@localhost:5432/hum_databank`)

3. **Setup Database**
   ```bash
   python -m flask db upgrade
   python -m flask create-admin
   ```

4. **Run Application**
   ```bash
   python run.py
   ```

   On Windows PowerShell, if `flask` commands fail, set: `$env:FLASK_APP = "run.py"`

## 📋 Key Files

### Core Application Files
- `run.py` – Main application entry point
- `requirements.txt` – Python dependencies
- `config/config.py` – Main configuration (loads from `.env` and environment)

### Configuration Files
- `config/` – Application configuration (e.g. `config/config.py`)
- `.env` – Environment variables (copy from `env.quickstart.example` or `env.example`)
- Docker: project root `docker-compose.yml` for DB and app services

### Documentation
- `docs/` – User guides, getting started, and engineering runbooks
- See `docs/README.md` for the full documentation index

### Scripts and Tools
- `scripts/` - Database migration and maintenance scripts
  - `scripts/trigger_automated_trace_review.py` – export pending/in-review/completed trace review packets to terminal or JSONL for automated batch triage.
  - `scripts/export_trace_reviews.py` – compatibility wrapper (deprecated) for the command above.
  - `scripts/seed_low_quality_review.py` – seed deterministic low-quality traces into the review queue for test/repro workflows.
- `tools/` - Development and debugging utilities

## 🔧 Development

### Prerequisites
- Python 3.x (3.9+ recommended; virtual environment optional but recommended)
- PostgreSQL (required; no SQLite fallback)
- LibreTranslate (optional; for translation services)

### Setup Development Environment
1. Clone the repository and `cd Backoffice`
2. (Optional) Create and activate a virtual environment: `python -m venv venv` then `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `env.quickstart.example` to `.env` and set `DATABASE_URL` (PostgreSQL)
5. Run database migrations: `python -m flask db upgrade` and create admin: `python -m flask create-admin`
6. Start the development server: `python run.py`

### Performance and Scaling Notes

- Database connection pool (production): tune via env vars
  - `SQLALCHEMY_POOL_SIZE` (default 20)
  - `SQLALCHEMY_MAX_OVERFLOW` (default 30)
  - `SQLALCHEMY_POOL_TIMEOUT` (default 60)
- Web server concurrency (Waitress): set `WEB_CONCURRENCY` to align with DB pool capacity.
  - A good starting point is `WEB_CONCURRENCY=8` with the default pool above.
  - Ensure total concurrent requests do not exceed available DB connections.

## 📚 Documentation

- **Full index:** [docs/README.md](docs/README.md) – getting started, user guides by role, engineering runbooks
- **Setup & optional features:** [docs/setup/](docs/setup/README.md) – LibreTranslate, AI, security (detailed)
- **API (when running):** Swagger UI at `/api-docs/`, OpenAPI at `/api-docs/openapi.json` or `/api-docs/openapi.yaml`

## 🌍 Internationalization

The platform supports multiple languages (multilingual indicators, sector translations). **LibreTranslate** is an optional service for automatic translations (EN, FR, ES, AR, ZH, RU, HI); it is disabled by default.

→ **Details:** [LibreTranslate setup](docs/setup/libretranslate.md) · [docs/README.md](docs/README.md) for user guides

## 🤖 AI chat and RAG

The backoffice includes an AI chat and RAG (document QA). You need at least one provider key (OpenAI, Gemini, or Azure) and `SECRET_KEY` for token signing. Optional: WebSockets (`flask-sock`), RAG (migrations + embedding env), Redis for rate limiting. Health: `GET /api/ai/v2/health`.

→ **Details:** [AI configuration](docs/setup/ai-configuration.md) · Full reference: **CLAUDE.md** (project root)

## 🔄 Data Migration

For database migrations use Flask-Migrate (`python -m flask db upgrade`). Optional future cleanup: [baseline squash checklist](migrations/README.md). For data migration procedures and scripts, see `scripts/` and `docs/` (index in `docs/README.md`).

## 🧪 AI review queue testing (dev)

```bash
# Export pending reviews as terminal packets
python scripts/trigger_automated_trace_review.py --status pending --limit 5 --format text

# Export as JSONL (for automation or batch processing)
python scripts/trigger_automated_trace_review.py --status pending --limit 20 --format jsonl --output pending_reviews.jsonl

# Seed a low-quality review item from latest trace
python scripts/seed_low_quality_review.py

# Seed from specific trace; create synthetic trace if missing
python scripts/seed_low_quality_review.py --trace-id 99999999 --create-trace-if-missing
```

## 📊 Analytics and Indicators

The ecosystem includes comprehensive analytics and indicator management (dynamic indicators, calculated lists, indicator bank, sector support). See `docs/README.md` and the user guides (e.g. Indicator Bank, reporting cycles) for details.

## 🤝 Contributing

1. Follow the established code structure
2. Update documentation when adding new features
3. Test thoroughly before submitting changes
4. Follow the migration procedures for database changes

## 🔒 Security

Set a strong `SECRET_KEY` in production (sessions, CSRF, tokens). Use `Authorization: Bearer` for API keys. Configure `CORS_ALLOWED_ORIGINS` in production. Rate limiting applies to auth, API, and plugin endpoints.

→ **Details:** [Security](docs/setup/security.md) – SECRET_KEY, CORS, rate limiting, file uploads, deployment checklist

## 📄 License

**License**

This backoffice component is part of the Humanitarian Databank ecosystem. See [LICENSE](../../LICENSE) for complete license terms.

For licensing inquiries, permissions, or questions about authorized use, please contact:
Haytham ALSOUFI: haythamsoufi@outlook.com 

# Backoffice — Critical Routes Coverage Matrix

Evidence artifact for ARB: each row lists a **production-critical route**, the automated test file that exercises it, and coverage status.

**Definition of covered:** integration test verifies (1) unauthenticated or unauthorized access is blocked, and (2) authorized happy path returns `200` or expected redirect.

| Route | Tier | Persona | Test file | Status |
|-------|------|---------|-----------|--------|
| `GET /health` | 1 | Public | `tests/integration/test_public_routes.py` | covered |
| `GET/POST /login`, `GET /logout` | 1 | All | `tests/integration/test_authentication.py` | covered |
| `GET/POST /` (dashboard) | 1 | Focal point | `tests/integration/test_critical_routes_focal.py` | covered |
| `POST /select_country/<id>` | 1 | Focal point | `tests/integration/test_critical_routes_focal.py` | covered |
| `GET/POST /forms/assignment/<aes_id>` | 1 | Focal point | `tests/integration/test_critical_routes_focal.py`, `tests/integration/test_entry_form_routes.py` | covered |
| `POST` save/submit assignment form | 1 | Focal point / Admin | `tests/integration/test_critical_routes_focal.py` | covered |
| `GET /excel/assignment/<aes_id>/export` | 2 | Admin | `tests/integration/test_excel_routes.py` | covered |
| `POST /approve_assignment/<aes_id>` | 2 | Org / SM | `tests/integration/test_critical_routes_focal.py` | covered |
| `POST /return_assignment_for_revision/<aes_id>` | 2 | Org / SM | `tests/integration/test_critical_routes_focal.py` | covered |
| `POST /reopen_assignment/<aes_id>` | 2 | Org / SM | `tests/integration/test_critical_routes_focal.py` | covered |
| `GET/POST /forms/public/<token>` | 3 | Public | `tests/integration/test_critical_routes_focal.py`, `tests/integration/test_entry_form_routes.py` | covered |
| `GET /form/<token>` (legacy redirect) | 3 | Public | `tests/integration/test_critical_routes_focal.py` | covered |
| `POST /request_country_access` | 3 | User | `tests/integration/test_critical_routes_focal.py` | covered |
| `GET /api/users/profile-summary` | 3 | Focal point | `tests/integration/test_critical_routes_focal.py`, `tests/integration/test_profile_summary_authorization.py` | covered |
| `GET /admin/` | 4 | System manager | `tests/integration/test_critical_routes_admin.py` (SM happy path; regular admin denied) | covered |
| `GET /admin/assignments` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/assignments/new` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/templates` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/users` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/access-requests` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/organization/` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/indicator_bank` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/public-submissions` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/api-management` | 4 | Admin | `tests/integration/test_critical_routes_admin.py` | covered |
| `GET /admin/api/system/health` (JSON) | 4 | Admin | `tests/integration/test_admin_smoke.py` | covered |
| `GET /api/v1/*` partner API | 1 | API key | `tests/api/test_api_*.py` | covered |
| `GET /api/mobile/*` | 1 | Mobile JWT | `tests/api/mobile/test_*.py` | covered |

## Running critical route tests only

```powershell
cd Backoffice
pytest -m critical -v
```

## Out of scope (deferred)

- Azure SSO (`/login/azure`, `/auth/azure/callback`)
- Form builder section/item CRUD (`/admin/templates/<id>/sections/*`)
- FDRS validation summary pages (`/forms/assignment_status/<aes_id>/validation_summary*`)

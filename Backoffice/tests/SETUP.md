# Test Setup Guide

## Required Environment Variables

For running tests, you need:

### Required
- **`TEST_DATABASE_URL`** (or `DATABASE_URL`) - PostgreSQL database connection string
- **`FLASK_CONFIG=testing`** - Set to 'testing' to use test configuration

### Optional (but recommended)
- **`SECRET_KEY`** - Secret key for testing (defaults to 'test-secret-key' if not set)

## Environment Variables

### Minimum Setup

```powershell
# PowerShell
$env:TEST_DATABASE_URL="postgresql://username:password@localhost:5432/test_db"
$env:FLASK_CONFIG="testing"
```

### Full Setup (recommended)

```powershell
# PowerShell
$env:TEST_DATABASE_URL="postgresql://username:password@localhost:5432/test_db"
$env:FLASK_CONFIG="testing"
$env:SECRET_KEY="test-secret-key"
$env:WTF_CSRF_ENABLED="false"
```

## Creating a Test Database

### Option 1: Using PostgreSQL Command Line

```powershell
# Connect to PostgreSQL
psql -U postgres

# Create test database
CREATE DATABASE test_db;

# Create user (optional, if you want a separate test user)
CREATE USER test_user WITH PASSWORD 'test_password';

# Grant privileges
GRANT ALL PRIVILEGES ON DATABASE test_db TO test_user;

# Exit psql
\q
```

Then set the environment variable:
```powershell
$env:TEST_DATABASE_URL="postgresql://test_user:test_password@localhost:5432/test_db"
```

### Option 2: Using pgAdmin

1. Open pgAdmin
2. Right-click on "Databases" → "Create" → "Database"
3. Name: `test_db`
4. Owner: `postgres` (or your user)
5. Click "Save"

### Option 3: Using SQL Script

Create a file `create_test_db.sql`:

```sql
-- Create test database
CREATE DATABASE test_db;

-- Create test user (optional)
CREATE USER test_user WITH PASSWORD 'test_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE test_db TO test_user;
```

Run it:
```powershell
psql -U postgres -f create_test_db.sql
```

### Option 4: Using Docker (if you have Docker)

```powershell
# Run PostgreSQL in Docker
docker run --name test-postgres `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=test_db `
  -p 5432:5432 `
  -d postgres:14

# Set environment variable
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/test_db"
```

## Database URL Format

The database URL format is:
```
postgresql://[username]:[password]@[host]:[port]/[database_name]
```

Examples:
- `postgresql://postgres:postgres@localhost:5432/test_db`
- `postgresql://test_user:test_pass@localhost:5432/test_db`
- `postgresql+psycopg2://user:pass@localhost:5432/test_db` (with driver)

## Running Tests

Once the database is set up:

```powershell
# Set environment variables
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/test_db"
$env:FLASK_CONFIG="testing"

# Run all tests
python -m pytest -v

# Or use the helper script
.\tests\run_tests.ps1
```

## Important Notes

⚠️ **NEVER use your production database for testing!**

- Tests will create and drop tables
- Tests may delete data
- Always use a separate test database
- The test database should be isolated from production data

## Troubleshooting

### "TEST_DATABASE_URL not set"
- Make sure you've set the environment variable in your current PowerShell session
- Check with: `$env:TEST_DATABASE_URL`

### "Connection refused" or "Cannot connect"
- Verify PostgreSQL is running: `Get-Service postgresql*`
- Check the connection string is correct
- Verify username/password are correct
- Check firewall settings

### "Database does not exist"
- Create the database first (see above)
- Verify the database name in the connection string

### "Permission denied"
- Grant proper privileges to the user
- Or use a user with superuser privileges for testing

## Quick Start Script

Save this as `setup_test_env.ps1`:

```powershell
# Setup test environment
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/test_db"
$env:FLASK_CONFIG="testing"
$env:SECRET_KEY="test-secret-key"

Write-Host "Test environment configured!" -ForegroundColor Green
Write-Host "TEST_DATABASE_URL: $env:TEST_DATABASE_URL" -ForegroundColor Cyan
Write-Host "FLASK_CONFIG: $env:FLASK_CONFIG" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run tests with: python -m pytest -v" -ForegroundColor Yellow
```

Then run:
```powershell
. .\setup_test_env.ps1
python -m pytest -v
```

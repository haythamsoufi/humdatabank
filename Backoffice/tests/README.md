# Testing Guide

This directory contains all tests for the Humanitarian Databank Backoffice, consolidated into a unified pytest-based testing system.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── unit/                    # Unit tests (fast, no database)
├── integration/             # Integration tests (require database)
│   ├── test_transaction_middleware.py
│   ├── test_static_cache.py
│   └── test_email.py
├── api/                     # API endpoint tests
│   └── test_api_endpoints.py
└── README.md                # This file
```

## Running Tests

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest tests/unit/ -m unit

# Integration tests only
pytest tests/integration/ -m integration

# API tests only
pytest tests/api/ -m api

# Transaction middleware tests
pytest -m transaction

# Static file tests
pytest -m static

# Email tests
pytest -m email
```

### Run with Coverage

```bash
# Generate coverage report
pytest --cov=app --cov-report=html

# View coverage report
# Open htmlcov/index.html in your browser
```

### Run Specific Test File

```bash
pytest tests/integration/test_transaction_middleware.py
```

### Run Specific Test

```bash
pytest tests/integration/test_transaction_middleware.py::TestTransactionMiddleware::test_managed_success_commits_and_removes
```

### Run in Parallel (faster)

```bash
pytest -n auto
```

## Test Markers

Tests are categorized using pytest markers:

- `@pytest.mark.unit` - Unit tests (fast, no database)
- `@pytest.mark.integration` - Integration tests (require database)
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.slow` - Slow running tests
- `@pytest.mark.db` - Tests that require database connection
- `@pytest.mark.email` - Email functionality tests
- `@pytest.mark.static` - Static file tests
- `@pytest.mark.transaction` - Transaction middleware tests

## Configuration

### Environment Variables

Tests require the following environment variables:

- `TEST_DATABASE_URL` or `DATABASE_URL` - PostgreSQL database URL for testing
- `FLASK_CONFIG=testing` - Use testing configuration

### Test Database

Tests use a separate test database (configured via `TEST_DATABASE_URL`). The test database is automatically created and cleaned up by pytest fixtures.

**Important**: Never use the production database for testing!

## Writing Tests

### Basic Test Structure

```python
import pytest
from app import db
from app.models import User

@pytest.mark.integration
class TestMyFeature:
    """Test my feature."""
    
    def test_something(self, client, db_session):
        """Test something."""
        # Your test code here
        response = client.get('/api/v1/endpoint')
        assert response.status_code == 200
```

### Using Fixtures

Common fixtures available in `conftest.py`:

- `app` - Flask application instance
- `client` - Flask test client
- `db_session` - Database session (auto-cleanup)
- `admin_user` - Admin user fixture
- `test_user` - Regular user fixture
- `logged_in_client` - Test client with logged-in admin
- `auth_headers` - Authentication headers
- `mock_email` - Mocked email sending
- `transaction_test_table` - Test table for transaction tests

### Example Test

```python
@pytest.mark.integration
@pytest.mark.api
class TestMyAPI:
    """Test my API endpoint."""
    
    def test_get_endpoint(self, client, auth_headers):
        """Test GET endpoint."""
        response = client.get(
            '/api/v1/my-endpoint',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert 'key' in data
    
    def test_post_endpoint(self, client, auth_headers, db_session):
        """Test POST endpoint."""
        response = client.post(
            '/api/v1/my-endpoint',
            headers=auth_headers,
            json={'key': 'value'}
        )
        assert response.status_code == 201
```

## Test Coverage

Current test coverage is tracked and reported. Aim for:

- **Minimum**: 50% coverage
- **Target**: 70%+ coverage
- **Critical paths**: 90%+ coverage

View coverage report:

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

## Continuous Integration

Tests should be run in CI/CD pipeline:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pytest --cov=app --cov-report=xml
```

## Migration from Old Tests

The old test files have been converted:

- `tests/test_transaction_middleware.py` → `tests/integration/test_transaction_middleware.py`
- `tests/test_transaction_middleware_db.py` → `tests/integration/test_transaction_middleware.py` (merged)
- `scripts/test_api_endpoints.py` → `tests/api/test_api_endpoints.py`
- `scripts/test_static_cache.py` → `tests/integration/test_static_cache.py`
- `scripts/test_email.py` → `tests/integration/test_email.py`

Old test files can be removed after verifying new tests work correctly.

## Troubleshooting

### Database Connection Issues

If tests fail with database connection errors:

1. Ensure `TEST_DATABASE_URL` is set
2. Verify database is accessible
3. Check database permissions

### Import Errors

If you see import errors:

1. Ensure you're in the project root directory
2. Verify `app` package is in Python path
3. Check that all dependencies are installed

### Fixture Errors

If fixtures fail:

1. Check `conftest.py` for fixture definitions
2. Verify fixture scope matches test needs
3. Ensure database is properly initialized

## Best Practices

1. **Use appropriate markers** - Mark tests correctly for easy filtering
2. **Keep tests fast** - Unit tests should be very fast (< 1 second)
3. **Use fixtures** - Don't duplicate setup code
4. **Test edge cases** - Don't just test happy paths
5. **Clean up** - Use fixtures for automatic cleanup
6. **Document tests** - Add docstrings explaining what's being tested
7. **Isolate tests** - Tests should not depend on each other
8. **Mock external services** - Don't make real API calls in tests

## Contributing

When adding new features:

1. Write tests first (TDD) or alongside code
2. Ensure all tests pass
3. Maintain or improve coverage
4. Update this README if adding new test categories

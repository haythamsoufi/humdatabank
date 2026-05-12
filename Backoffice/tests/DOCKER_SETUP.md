# Test Database Setup in Docker

## Quick Start

The test database is automatically created when you start the Docker service. Here's how to set it up:

### 1. Start the Test Database Service

```bash
# Start only the test database (useful for testing)
docker-compose up -d db-test

# Or start all services (including test database)
docker-compose up -d
```

### 2. Verify the Test Database is Running

```bash
# Check if the container is running
docker ps | grep hum-databank-postgres-test

# Check the logs
docker-compose logs db-test

# Test the connection (from host machine)
docker exec -it hum-databank-postgres-test psql -U app -d hum_databank_test -c "SELECT version();"
```

### 3. Run Migrations on Test Database (Optional)

The test database will be automatically set up by pytest fixtures using `db.create_all()`, but if you want to run migrations manually:

```bash
# Run migrations on test database
docker-compose run --rm backoffice sh -c "
  export DATABASE_URL=postgresql+psycopg2://app:app@db-test:5432/hum_databank_test
  export FLASK_CONFIG=testing
  flask db upgrade
"
```

### 4. Run Tests

```bash
# Run tests inside the Docker container (recommended)
docker-compose exec backoffice pytest

# Or run tests from your host machine (make sure TEST_DATABASE_URL points to port 5433)
export TEST_DATABASE_URL=postgresql+psycopg2://app:app@localhost:5433/hum_databank_test
pytest
```

## Connection Details

- **Container name**: `hum-databank-postgres-test`
- **Database name**: `hum_databank_test` (configurable via `POSTGRES_DB_TEST` env var)
- **Username**: `app` (configurable via `POSTGRES_USER` env var)
- **Password**: `app` (configurable via `POSTGRES_PASSWORD` env var)
- **Port (host)**: `5433` (maps to container port `5432`)
- **Port (container network)**: `5432`

## Connection Strings

### From Inside Docker Containers
```
postgresql+psycopg2://app:app@db-test:5432/hum_databank_test
```

### From Host Machine
```
postgresql+psycopg2://app:app@localhost:5433/hum_databank_test
```

## Environment Variables

You can customize the test database by setting these in your `.env` file or environment:

```bash
POSTGRES_USER=app                    # Database user (default: app)
POSTGRES_PASSWORD=app               # Database password (default: app)
POSTGRES_DB_TEST=hum_databank_test  # Test database name (default: hum_databank_test)
```

## Troubleshooting

### Database Already Exists Error
If you see errors about the database already existing, you can reset it:

```bash
# Stop and remove the test database container and volume
docker-compose down db-test
docker volume rm <compose_project_name>_pgdata_test

# Start fresh
docker-compose up -d db-test
```

### Connection Refused
Make sure the test database service is running:
```bash
docker-compose ps db-test
```

### Port Already in Use
If port 5433 is already in use, you can change it in `docker-compose.yml`:
```yaml
ports:
  - "5434:5432"  # Change 5433 to 5434 or another available port
```

## Clean Up

To completely remove the test database:

```bash
# Stop and remove container
docker-compose down db-test

# Remove the volume (deletes all test data)
docker volume rm <compose_project_name>_pgdata_test
```

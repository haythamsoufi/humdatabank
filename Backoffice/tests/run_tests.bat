@echo off
setlocal EnableDelayedExpansion

REM Interactive pytest wizard for Backoffice.
REM Usage:  tests\run_tests.bat   (from Backoffice/)  or double-click from tests\

cd /d "%~dp0\.."

title Backoffice Test Runner

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    exit /b 1
)

REM Load Backoffice\.env (override=False — keeps any vars already in the shell)
set "ENV_CMD=%TEMP%\backoffice_test_env_%RANDOM%.cmd"
python "%~dp0load_backoffice_env.py" --emit-cmd "%ENV_CMD%" >nul 2>&1
if exist "%ENV_CMD%" (
    call "%ENV_CMD%"
    del "%ENV_CMD%"
)

REM Test runners always use the testing config (override .env FLASK_CONFIG=development).
set "FLASK_CONFIG=testing"

echo.
echo ============================================================
echo   Humanitarian Databank - Backoffice Test Runner
echo ============================================================
echo   Working directory: %CD%
echo.

if defined TEST_DATABASE_URL (
    echo Database: TEST_DATABASE_URL loaded.
) else if defined DATABASE_URL (
    echo Database: DATABASE_URL loaded.
) else if exist ".env" (
    echo WARNING: Backoffice\.env exists but TEST_DATABASE_URL / DATABASE_URL not found.
    echo          Integration and API tests may fail without PostgreSQL.
    echo.
) else (
    echo WARNING: Backoffice\.env not found and no database URL in environment.
    echo          Integration and API tests may fail without PostgreSQL.
    echo.
)

REM --- 1. Test scope --------------------------------------------------------
echo  What do you want to run?
echo    [1] All tests
echo    [2] Unit only          ^(-m unit^)
echo    [3] Integration only   ^(-m integration^)
echo    [4] API only           ^(-m api^)
echo    [5] Fast               ^(-m "not slow" — skip integration/API^)
echo    [6] Custom path/file   ^(e.g. tests\unit\test_middleware\^)
echo    [7] By marker          ^(pick from registered markers^)
echo.
choice /C 1234567 /N /M "Select scope [1-7]: "
set "SCOPE_CHOICE=!errorlevel!"

set "PYTEST_TARGETS=tests"
set "MARKER_EXPR="

if !SCOPE_CHOICE!==2 set "MARKER_EXPR=unit"
if !SCOPE_CHOICE!==3 set "MARKER_EXPR=integration"
if !SCOPE_CHOICE!==4 set "MARKER_EXPR=api"
if !SCOPE_CHOICE!==5 set "MARKER_EXPR=not slow"
if !SCOPE_CHOICE!==6 (
    set /p "PYTEST_TARGETS=Enter path (relative to Backoffice): "
    if "!PYTEST_TARGETS!"=="" (
        echo ERROR: Path required.
        exit /b 1
    )
)
if !SCOPE_CHOICE!==7 (
    echo.
    echo  Select marker ^(see pytest.ini^):
    echo    [1] critical       - production route smoke tests
    echo    [2] transaction    - transaction middleware tests
    echo    [3] auth_security  - auth routes, authorization, auth forms
    echo    [4] email          - email functionality tests
    echo    [5] static         - static file tests
    echo    [6] db             - tests requiring database
    echo    [7] slow           - slow tests ^(integration/API^)
    echo    [8] unit           - unit tests
    echo    [9] integration    - integration tests
    echo    [A] api            - API endpoint tests
    echo    [B] Custom         - type your own expression
    echo.
    choice /C 123456789AB /N /M "Select marker [1-9,A,B]: "
    set "MARKER_CHOICE=!errorlevel!"
    if !MARKER_CHOICE!==1 set "MARKER_EXPR=critical"
    if !MARKER_CHOICE!==2 set "MARKER_EXPR=transaction"
    if !MARKER_CHOICE!==3 set "MARKER_EXPR=auth_security"
    if !MARKER_CHOICE!==4 set "MARKER_EXPR=email"
    if !MARKER_CHOICE!==5 set "MARKER_EXPR=static"
    if !MARKER_CHOICE!==6 set "MARKER_EXPR=db"
    if !MARKER_CHOICE!==7 set "MARKER_EXPR=slow"
    if !MARKER_CHOICE!==8 set "MARKER_EXPR=unit"
    if !MARKER_CHOICE!==9 set "MARKER_EXPR=integration"
    if !MARKER_CHOICE!==10 set "MARKER_EXPR=api"
    if !MARKER_CHOICE!==11 (
        set /p "MARKER_EXPR=Enter marker expression (without -m): "
        if "!MARKER_EXPR!"=="" (
            echo ERROR: Marker expression required.
            exit /b 1
        )
    )
    if "!MARKER_EXPR!"=="" (
        echo ERROR: Invalid marker selection.
        exit /b 1
    )
)

echo.

REM --- 2. Parallelism -------------------------------------------------------
echo  Parallel workers (requires pytest-xdist in requirements-dev.txt):
echo    [1] Sequential  ^(no -n^)
echo    [2] Auto        ^(-n auto^)
echo    [3] Custom count
echo.
choice /C 123 /N /M "Select parallelism [1-3]: "
set "PAR_CHOICE=!errorlevel!"

set "PYTEST_PARALLEL="
if !PAR_CHOICE!==2 set "PYTEST_PARALLEL=-n auto"
if !PAR_CHOICE!==3 (
    set /p "WORKERS=Number of workers: "
    if "!WORKERS!"=="" (
        echo ERROR: Worker count required.
        exit /b 1
    )
    set "PYTEST_PARALLEL=-n !WORKERS!"
)

echo.

REM --- 3. Coverage ----------------------------------------------------------
echo  Coverage:
echo    [1] Off           ^(--no-cov, fastest^)
echo    [2] Full refresh  ^(erase .coverage, full HTML + XML^)
echo    [3] Append        ^(merge into existing .coverage / htmlcov^)
echo    [4] Reports only  ^(--cov=app, overwrite .coverage, HTML + XML^)
echo.
choice /C 1234 /N /M "Select coverage [1-4]: "
set "COV_CHOICE=!errorlevel!"

set "PYTEST_COV=--no-cov"
set "COV_ERASE="

if !COV_CHOICE!==2 (
    set "COV_ERASE=1"
    set "PYTEST_COV=--cov=app --cov-report=term-missing --cov-report=html:htmlcov --cov-report=xml:coverage.xml"
)
if !COV_CHOICE!==3 (
    set "PYTEST_COV=--cov=app --cov-append --cov-report=term-missing --cov-report=html:htmlcov"
)
if !COV_CHOICE!==4 (
    set "PYTEST_COV=--cov=app --cov-report=term-missing --cov-report=html:htmlcov --cov-report=xml:coverage.xml"
)

echo.

REM --- 4. Extra options -----------------------------------------------------
set "PYTEST_EXTRA="
choice /C YN /N /M "Stop on first failure (-x)? [Y/N]: "
if !errorlevel!==1 set "PYTEST_EXTRA=!PYTEST_EXTRA! -x"

choice /C YN /N /M "Show 20 slowest tests (--durations=20)? [Y/N]: "
if !errorlevel!==1 set "PYTEST_EXTRA=!PYTEST_EXTRA! --durations=20"

echo.

REM --- Preview command ------------------------------------------------------
echo ------------------------------------------------------------
echo  Command preview:
if defined MARKER_EXPR (
    echo    python -m pytest !PYTEST_TARGETS! -m "!MARKER_EXPR!" !PYTEST_COV! !PYTEST_PARALLEL! !PYTEST_EXTRA!
) else (
    echo    python -m pytest !PYTEST_TARGETS! !PYTEST_COV! !PYTEST_PARALLEL! !PYTEST_EXTRA!
)
echo ------------------------------------------------------------
echo.

if defined COV_ERASE (
    echo Erasing previous coverage data...
    python -m coverage erase
    if errorlevel 1 (
        echo WARNING: coverage erase failed; continuing anyway.
    )
    echo.
)

echo Running...
echo.

if defined MARKER_EXPR (
    python -m pytest !PYTEST_TARGETS! -m "!MARKER_EXPR!" !PYTEST_COV! !PYTEST_PARALLEL! !PYTEST_EXTRA!
) else (
    python -m pytest !PYTEST_TARGETS! !PYTEST_COV! !PYTEST_PARALLEL! !PYTEST_EXTRA!
)
set "EXIT_CODE=!errorlevel!"

echo.
if !EXIT_CODE!==0 (
    echo Done. All tests passed.
) else (
    echo Done. Exit code: !EXIT_CODE!
)

if !COV_CHOICE!==2 (
    echo Coverage: htmlcov\index.html  and  coverage.xml
) else if !COV_CHOICE!==3 (
    echo Coverage appended. Open htmlcov\index.html
) else if !COV_CHOICE!==4 (
    echo Coverage: htmlcov\index.html  and  coverage.xml
)

echo Full log: test_results.log
echo.

exit /b !EXIT_CODE!

@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  Humanitarian Databank Mobile
echo.

echo  Action:
echo    1^) Run on device/emulator
echo    2^) Build release APK
echo.
set "ACTION_CHOICE=1"
set /p "ACTION_CHOICE=  Choice [1-2, Enter=run]: "
if "!ACTION_CHOICE!"=="" set "ACTION_CHOICE=1"

if not "!ACTION_CHOICE!"=="1" if not "!ACTION_CHOICE!"=="2" (
  echo  Invalid action choice. Exiting.
  exit /b 1
)

echo.
echo  Backoffice URL:
echo    1^) https://databank.ifrc.org
echo    2^) https://databank-stage.ifrc.org
echo    3^) https://backoffice-databank.fly.dev
echo    4^) http://10.0.2.2:5000
echo    5^) http://localhost:5000
echo    6^) Custom URL
echo.
set /p "BO_CHOICE=  Choice [1-6]: "

set "BACKEND_URL="
if "!BO_CHOICE!"=="1" set "BACKEND_URL=https://databank.ifrc.org"
if "!BO_CHOICE!"=="2" set "BACKEND_URL=https://databank-stage.ifrc.org"
if "!BO_CHOICE!"=="3" set "BACKEND_URL=https://backoffice-databank.fly.dev"
if "!BO_CHOICE!"=="4" set "BACKEND_URL=http://10.0.2.2:5000"
if "!BO_CHOICE!"=="5" set "BACKEND_URL=http://localhost:5000"
if "!BO_CHOICE!"=="6" (
  set /p "BACKEND_URL=  Enter backoffice URL: "
)

if not defined BACKEND_URL (
  echo  Invalid or empty choice. Exiting.
  exit /b 1
)

set "FRONTEND_URL=https://website-databank.fly.dev"

echo.
echo  BACKEND_URL=!BACKEND_URL!
echo  FRONTEND_URL=!FRONTEND_URL!
echo.

REM Merge into .env (preserve other keys; replace BACKEND_URL / FRONTEND_URL / MOBILE_APP_API_KEY)
REM MOBILE_APP_API_KEY is filled from MOBILE_APP_API_KEY_IFRC_PROD / _IFRC_STAGING / _LOCAL_DEV for choices 1,2,5; otherwise previous MOBILE_APP_API_KEY is kept.
set "BO_CHOICE=!BO_CHOICE!"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$envFile = Join-Path (Get-Location) '.env';" ^
  "$b = $env:BACKEND_URL.Trim().TrimEnd('/');" ^
  "$f = $env:FRONTEND_URL.Trim().TrimEnd('/');" ^
  "$choice = ($env:BO_CHOICE + '').Trim();" ^
  "$map = @{};" ^
  "if (Test-Path $envFile) {" ^
  "  Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {" ^
  "    $line = $_;" ^
  "    if ($line -match '^\s*#' -or $line -notmatch '=') { return };" ^
  "    $i = $line.IndexOf('='); if ($i -lt 1) { return };" ^
  "    $k = $line.Substring(0, $i).Trim(); $v = $line.Substring($i + 1);" ^
  "    $map[$k] = $v;" ^
  "  }" ^
  "};" ^
  "$mobile = $null;" ^
  "switch ($choice) {" ^
  "  '1' { $mobile = $map['MOBILE_APP_API_KEY_IFRC_PROD'] }" ^
  "  '2' { $mobile = $map['MOBILE_APP_API_KEY_IFRC_STAGING'] }" ^
  "  '5' { $mobile = $map['MOBILE_APP_API_KEY_LOCAL_DEV'] }" ^
  "  default { $mobile = $map['MOBILE_APP_API_KEY'] }" ^
  "};" ^
  "if ($null -eq $mobile) { $mobile = '' };" ^
  "$lines = @();" ^
  "if (Test-Path $envFile) { $lines = @(Get-Content -LiteralPath $envFile -Encoding UTF8 | Where-Object { $_ -notmatch '^(BACKEND_URL|FRONTEND_URL|MOBILE_APP_API_KEY)=' }) };" ^
  "$lines += ('BACKEND_URL=' + $b);" ^
  "$lines += ('FRONTEND_URL=' + $f);" ^
  "$lines += ('MOBILE_APP_API_KEY=' + $mobile);" ^
  "Set-Content -LiteralPath $envFile -Value $lines -Encoding UTF8;"

if errorlevel 1 (
  echo  Failed to update .env
  exit /b 1
)

echo  Updated .env
echo.

if "!BO_CHOICE!"=="5" (
  adb reverse tcp:5000 tcp:5000
  if errorlevel 1 (
    echo  Warning: adb reverse failed. Connect one device with USB debugging, or ensure adb is on PATH.
  )
  echo.
)

REM Stop Gradle daemons so Windows can delete mergeDebugAssets (avoids kernel_blob.bin lock errors)
if exist "android\gradlew.bat" (
  if exist "%ProgramFiles%\Android\Android Studio\jbr" (
    set "JAVA_HOME=%ProgramFiles%\Android\Android Studio\jbr"
  )
  call android\gradlew.bat --stop >nul 2>&1
)

if /i "!ACTION_CHOICE!"=="2" (
  echo  Building APK...
  echo.
  flutter build apk %*
) else (
  echo  Starting Flutter run...
  echo.
  flutter run %*
)

endlocal
exit /b %ERRORLEVEL%

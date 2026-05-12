@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  Humanitarian Databank Mobile — choose Backoffice URL
echo  (writes BACKEND_URL + FRONTEND_URL + MOBILE_APP_API_KEY into MobileApp\.env)
echo.
echo  API keys: add these once in MobileApp\.env — this script sets MOBILE_APP_API_KEY from them:
echo    MOBILE_APP_API_KEY_IFRC_PROD     — choice 1 ^(IFRC production^)
echo    MOBILE_APP_API_KEY_IFRC_STAGING  — choice 2 ^(IFRC staging^)
echo    MOBILE_APP_API_KEY_LOCAL_DEV     — choice 5 ^(local dev^)
echo  Mapbox ^(optional^): add MAPBOX_ACCESS_TOKEN=pk... to .env for IFRC-style map tiles;
echo    or pass  --dart-define=MAPBOX_ACCESS_TOKEN=pk...  ^(also forwarded from extra args below^).
echo.

echo  Backoffice (Flask / API^):
echo    1^) https://databank.ifrc.org              (IFRC production — default prod API host^)
echo    2^) https://databank-stage.ifrc.org          (IFRC staging^)
echo    3^) https://backoffice-databank.fly.dev     (Fly.io preview — not the same as 1^)
echo    4^) http://10.0.2.2:5000   (Android emulator: host machine localhost:5000)
echo    5^) http://localhost:5000   (USB phone: adb reverse tcp:5000 tcp:5000 first^)
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
echo  FRONTEND_URL=!FRONTEND_URL! ^(fixed^)
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
if "!BO_CHOICE!"=="1" echo   MOBILE_APP_API_KEY ^<= MOBILE_APP_API_KEY_IFRC_PROD
if "!BO_CHOICE!"=="2" echo   MOBILE_APP_API_KEY ^<= MOBILE_APP_API_KEY_IFRC_STAGING
if "!BO_CHOICE!"=="5" echo   MOBILE_APP_API_KEY ^<= MOBILE_APP_API_KEY_LOCAL_DEV
if "!BO_CHOICE!"=="3" echo   MOBILE_APP_API_KEY ^(unchanged / same as last .env^)
if "!BO_CHOICE!"=="4" echo   MOBILE_APP_API_KEY ^(unchanged / same as last .env^)
if "!BO_CHOICE!"=="6" echo   MOBILE_APP_API_KEY ^(unchanged / same as last .env^)
echo.

if "!BO_CHOICE!"=="5" (
  echo  USB phone: adb reverse tcp:5000 tcp:5000
  adb reverse tcp:5000 tcp:5000
  if errorlevel 1 (
    echo  Warning: adb reverse failed. Connect one device with USB debugging, or ensure adb is on PATH.
  )
  echo.
)

echo  Action:
echo    1^) Run on device/emulator ^(flutter run — default^)
echo    2^) Build release APK ^(flutter build apk^)
echo.
set "ACTION_CHOICE=1"
set /p "ACTION_CHOICE=  Choice [1-2, Enter=run]: "
if "!ACTION_CHOICE!"=="" set "ACTION_CHOICE=1"

if /i "!ACTION_CHOICE!"=="2" (
  echo.
  echo  Building APK. Extra args: %*
  echo.
  flutter build apk %*
) else (
  echo.
  echo  Starting Flutter run ^(default org profile: IFRC^). Extra args: %*
  echo.
  flutter run %*
)

endlocal
exit /b %ERRORLEVEL%

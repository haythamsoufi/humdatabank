@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem GB Report - interactive build menu
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "SCRIPTS=%ROOT%\scripts"
set "REPORT_OUT=%ROOT%\report\output"
set "HTML=%REPORT_OUT%\gb-report.html"
set "EXCEL=%ROOT%\SG Report.xlsx"
set "EXCEL_COPY=%ROOT%\SG Report._build.xlsx"
set "PYTHON=python"
set "FIGURE_STYLE=professional"

cd /d "%ROOT%"

:menu
cls
echo.
echo  ========================================================
echo   GB Report Builder - July 2026
echo  ========================================================
echo.
echo   Data:  SG Report.xlsx
echo   HTML:  report\output\gb-report.html
echo   Style: %FIGURE_STYLE%
echo.
echo   1. Build full report      (figures + HTML)
echo   2. Regenerate figures only
echo   3. Build Word only        (all languages, editable)
echo   4. Exit
echo   5. Install Python dependencies
echo   6. Install Playwright Chromium
echo   7. Change figure style    (classic / modern / professional)
echo.
set "CHOICE="
set /p "CHOICE=Select option [1-7]: "

if "%CHOICE%"=="1" goto build_full
if "%CHOICE%"=="2" goto build_figures
if "%CHOICE%"=="3" goto build_word
if "%CHOICE%"=="4" goto end
if "%CHOICE%"=="5" goto install_deps
if "%CHOICE%"=="6" goto install_playwright
if "%CHOICE%"=="7" goto pick_style
echo Invalid choice.
pause
goto menu

:check_python
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python not found. Install Python 3.11+ and ensure it is on PATH.
    pause
    goto menu
)
goto :eof

:prepare_excel
set "GB_REPORT_EXCEL="
if exist "%EXCEL%" (
    rem Try to create a fresh copy for the build (avoids Excel lock errors)
    powershell -NoProfile -Command "Copy-Item -LiteralPath '%EXCEL%' -Destination '%EXCEL_COPY%' -Force" >nul 2>&1
    if not errorlevel 1 (
        set "GB_REPORT_EXCEL=%EXCEL_COPY%"
    )
)
goto :eof

:cleanup_excel
set "GB_REPORT_EXCEL="
if exist "%EXCEL_COPY%" del /f /q "%EXCEL_COPY%" >nul 2>&1
goto :eof

:pick_style
cls
echo.
echo  Figure style
echo  ------------
echo   1. classic       Tableau-faithful default
echo   2. modern        area fill, shadow, marker rings
echo   3. professional  marker rings, thinner stroke
echo   4. Back
echo.
set "STYLE_CHOICE="
set /p "STYLE_CHOICE=Select style [1-4]: "
if "%STYLE_CHOICE%"=="1" set "FIGURE_STYLE=classic" & goto menu
if "%STYLE_CHOICE%"=="2" set "FIGURE_STYLE=modern" & goto menu
if "%STYLE_CHOICE%"=="3" set "FIGURE_STYLE=professional" & goto menu
if "%STYLE_CHOICE%"=="4" goto menu
echo Invalid choice.
pause
goto pick_style

:build_full
call :check_python
echo.
echo Building full report (style: %FIGURE_STYLE%)...
call :prepare_excel
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "GB_FIGURES_STYLE=%FIGURE_STYLE%"
cd /d "%SCRIPTS%"
%PYTHON% build_report.py --format html --style %FIGURE_STYLE%
set "ERR=!errorlevel!"
cd /d "%ROOT%"
call :cleanup_excel
echo.
if !ERR! neq 0 (
    echo Build failed. Close SG Report.xlsx in Excel and try again.
) else (
    echo Done. HTML report: report\output\gb-report.html
    echo Word documents: report\output\gb-report-*.docx
    echo PDF documents:  report\output\gb-report-*.pdf
    echo Dashboard PNGs: Figures\
)
pause
goto menu

:build_figures
call :check_python
echo.
echo Regenerating figures (style: %FIGURE_STYLE%)...
call :prepare_excel
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "GB_FIGURES_STYLE=%FIGURE_STYLE%"
cd /d "%SCRIPTS%"
%PYTHON% build_report.py --figures-only --style %FIGURE_STYLE%
set "ERR=!errorlevel!"
cd /d "%ROOT%"
call :cleanup_excel
echo.
if !ERR! neq 0 (echo Figure generation failed.) else (echo Figures written to Figures\ and report\figures\)
pause
goto menu

:build_word
call :check_python
echo.
echo Building Word documents (style: %FIGURE_STYLE%)...
call :prepare_excel
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "GB_FIGURES_STYLE=%FIGURE_STYLE%"
cd /d "%SCRIPTS%"
%PYTHON% generate_report_docx.py --all-languages
set "ERR=!errorlevel!"
cd /d "%ROOT%"
call :cleanup_excel
echo.
if !ERR! neq 0 (echo Word build failed.) else (echo DOCX files written to report\output\)
pause
goto menu

:install_deps
call :check_python
echo.
echo Installing Python dependencies...
%PYTHON% -m pip install -r "%ROOT%\requirements.txt"
echo.
if errorlevel 1 (echo Dependency install failed.) else (echo Dependencies installed.)
pause
goto menu

:install_playwright
call :check_python
echo.
echo Installing Playwright Chromium...
%PYTHON% -m playwright install chromium
echo.
if errorlevel 1 (echo Playwright install failed.) else (echo Playwright Chromium installed.)
pause
goto menu

:end
call :cleanup_excel
endlocal
exit /b 0

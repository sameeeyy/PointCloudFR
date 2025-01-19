@echo off
setlocal EnableDelayedExpansion

REM Find QGIS in Program Files
for /d %%i in ("C:\Program Files\QGIS*") do (
    if exist "%%i\bin\qgis-bin.exe" (
        set "OSGEO4W_ROOT=%%i"
    )
)

if not defined OSGEO4W_ROOT (
    echo QGIS installation not found!
    exit /b 1
)

REM Set up basic environment
set "PATH=%OSGEO4W_ROOT%\bin;%PATH%"
set "PATH=%PATH%;%OSGEO4W_ROOT%\apps\qgis\bin"

REM Call standard environment setup
call "%OSGEO4W_ROOT%\bin\o4w_env.bat"
call "%OSGEO4W_ROOT%\bin\qt5_env.bat"
call "%OSGEO4W_ROOT%\bin\py3_env.bat"

REM Ensure QGIS bin is in front of PATH
path %OSGEO4W_ROOT%\apps\qgis\bin;%PATH%

REM Change to script directory
cd /d %~dp0

echo Using QGIS from: %OSGEO4W_ROOT%
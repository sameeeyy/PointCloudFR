@echo ON

cd /d %~dp0

REM Try with QGIS Python first
call "py3-env.bat"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

REM If the above fails, try with system Python
IF %ERRORLEVEL% NEQ 0 (
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
)

pause
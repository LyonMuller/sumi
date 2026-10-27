@echo off
setlocal
cd /d "%~dp0"
python -c "import struct,sys; sys.exit(0 if sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 goto :error
python -m venv .venv
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.lock.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" setup_models.py
if errorlevel 1 goto :error
echo Pronto. Execute INICIAR.bat.
pause
exit /b 0
:error
echo Falha de instalacao. Recomendado Python 3.14 x64. Consulte README.md.
pause
exit /b 1

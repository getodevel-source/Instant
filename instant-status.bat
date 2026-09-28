@echo off
REM Diagnostico rapido: NO levanta el daemon, solo lo inspecciona.
REM Modelos: %~dp0models [relativo al repo]. Solo default, respeta DICTADO_DATA previa.
setlocal
if not defined DICTADO_DATA set "DICTADO_DATA=%~dp0models"
echo == proceso ==
set "PIDFILE=%APPDATA%\instant\instant.pid"
if not exist "%PIDFILE%" goto :nopid
set /p LEPID=<"%PIDFILE%"
if not defined LEPID goto :emptypid
tasklist /FI "PID eq %LEPID%" /FO TABLE /NH 2>nul | findstr /I "instant.exe python.exe pythonw.exe" >nul
if errorlevel 1 goto :stalepid
echo vivo: SI PID %LEPID%
goto :models
:stalepid
echo vivo: NO PID %LEPID% stale; el proceso murio.
del "%PIDFILE%" 2>nul
echo PID file stale limpio.
goto :models
:emptypid
echo PID file vacio; se limpia.
del "%PIDFILE%" 2>nul
goto :scanlegacy
:nopid
goto :scanlegacy
:scanlegacy
tasklist /FI "IMAGENAME eq instant.exe" 2>nul | findstr /I "instant.exe" >nul
if not errorlevel 1 goto :legacy_exe
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*instant*' }) { exit 1 } else { exit 0 }" >nul 2>nul
if errorlevel 1 goto :legacy_pyw
echo vivo: NO
goto :models
:legacy_exe
echo vivo: SI instant.exe sin PID file, lanzado con version vieja.
goto :models
:legacy_pyw
echo vivo: SI pythonw oculto sin PID file, lanzado con version vieja.
goto :models
:models
echo == modelos ==
echo DICTADO_DATA=%DICTADO_DATA%
if defined DICTADO_DATA goto :hasdata
echo var vacia: el exe usaria el default %LOCALAPPDATA%\instant\models
if exist "%LOCALAPPDATA%\instant\models\parakeet-v3-int8\encoder.int8.onnx" goto :defok
echo default %LOCALAPPDATA%\instant\models: VACIO - fija DICTADO_DATA o usa instant-run.bat
goto :log
:hasdata
if exist "%DICTADO_DATA%\parakeet-v3-int8\encoder.int8.onnx" goto :dataok
echo dir DICTADO_DATA: VACIO o sin modelos, revisa la ruta.
goto :log
:dataok
echo dir DICTADO_DATA: OK encoder.int8.onnx presente.
goto :log
:defok
echo default %LOCALAPPDATA%\instant\models: OK
:log
echo.
echo == log: ultimas 15 lineas de %%APPDATA%%\instant\instant.log ==
powershell -NoProfile -Command "Get-Content \"$env:APPDATA\instant\instant.log\" -Tail 15"
echo.
echo == config: %%APPDATA%%\instant\config.json ==
type "%APPDATA%\instant\config.json"

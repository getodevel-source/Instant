@echo off
REM instant-run: SIN args -> arranca el daemon OCULTO [sin ventana visible].
REM Con args -> passthrough en consola [ej. instant-run.bat --help, run, check].
REM Sin duplicados: si ya hay instancia viva [PID file o tasklist], avisa y sale.
REM Modelos: %~dp0models [relativo al repo]. Solo default, respeta DICTADO_DATA previa.
setlocal
if not defined DICTADO_DATA set "DICTADO_DATA=%~dp0models"
if not "%~1"=="" goto :foreground
set "PIDFILE=%APPDATA%\instant\instant.pid"
if exist "%PIDFILE%" goto :checkpid
goto :scan
:checkpid
set /p LEPID=<"%PIDFILE%"
if not defined LEPID goto :stale
tasklist /FI "PID eq %LEPID%" /FO TABLE /NH 2>nul | findstr /I "instant.exe python.exe pythonw.exe" >nul
if errorlevel 1 goto :stale
echo Ya hay instancia viva PID %LEPID%. No se lanza otra. Usa instant-status.bat.
exit /b 0
:stale
del "%PIDFILE%" 2>nul
:scan
REM Solo el DAEMON cuenta (...\instant... run...), no la GUI (setup/home):
REM antes cualquier Instant.exe (incluida la ventana de ajustes) bloqueaba
REM el arranque del daemon (falso positivo).
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'Instant.exe' -or $_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -like '*instant*run*' }) { exit 1 } else { exit 0 }" >nul 2>nul
if errorlevel 1 goto :dup_exe
goto :launch
:dup_exe
echo Ya hay daemon vivo sin PID file. No se lanza otro.
exit /b 0
:launch
set "INSTANT_PYTHON=%~dp0.venv\Scripts\pythonw.exe"
if exist "%INSTANT_PYTHON%" goto :start_hidden
set "INSTANT_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%INSTANT_PYTHON%" goto :start_hidden
set "INSTANT_PYTHON="
for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined INSTANT_PYTHON set "INSTANT_PYTHON=%%P"
if not defined INSTANT_PYTHON (
  for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined INSTANT_PYTHON set "INSTANT_PYTHON=%%P"
)
if not defined INSTANT_PYTHON goto :fail
:start_hidden
set "INSTANT_WORKDIR=%~dp0"
powershell -NoProfile -Command "try { Start-Process -FilePath $env:INSTANT_PYTHON -ArgumentList '-m instant_app run' -WindowStyle Hidden -WorkingDirectory $env:INSTANT_WORKDIR; exit 0 } catch { Write-Error $_; exit 1 }"
if errorlevel 1 goto :fail
echo Daemon lanzado oculto sin ventana. Verifica con instant-status.bat; frena con instant-stop.bat.
exit /b 0
:fail
echo ERROR: no se pudo lanzar el daemon oculto.
exit /b 1
:foreground
if exist "%~dp0.venv\Scripts\python.exe" goto :fg_venv
where instant.exe >nul 2>nul
if %ERRORLEVEL%==0 goto :fg_exe
goto :fg_python
:fg_venv
"%~dp0.venv\Scripts\python.exe" -m instant_app %*
exit /b %ERRORLEVEL%
:fg_exe
instant.exe %*
exit /b %ERRORLEVEL%
:fg_python
python -m instant_app %*
exit /b %ERRORLEVEL%

@echo off
REM Abre el asistente de configuración de Instant.
setlocal
set "ROOT=%~dp0.."
if not defined DICTADO_DATA set "DICTADO_DATA=%ROOT%\models"
pushd "%ROOT%"

if not "%~1"=="" goto :console
if exist "%ROOT%\dist\Instant.exe" goto :launch_gui_exe
if exist "%ROOT%\.venv\Scripts\pythonw.exe" goto :launch_venv_gui
goto :path_pythonw

:launch_gui_exe
start "" "%ROOT%\dist\Instant.exe" setup
goto :done

:launch_venv_gui
start "" "%ROOT%\.venv\Scripts\pythonw.exe" -m instant_app setup
goto :done

:path_pythonw
set "INSTANT_PYTHONW="
for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined INSTANT_PYTHONW set "INSTANT_PYTHONW=%%P"
if defined INSTANT_PYTHONW goto :system_pythonw
echo [Instant] No encuentro Instant.exe ni pythonw.exe para abrir la interfaz.
set "SETUP_RC=1"
goto :finish

:system_pythonw
start "" "%INSTANT_PYTHONW%" -m instant_app setup
goto :done

:console
if exist "%ROOT%\.venv\Scripts\python.exe" (
  call "%ROOT%\.venv\Scripts\python.exe" -m instant_app setup %*
  goto :done
)

where instant.exe >nul 2>nul
if not errorlevel 1 (
  call instant.exe setup %*
  goto :done
)
call python -m instant_app setup %*

:done
set "SETUP_RC=%ERRORLEVEL%"
:finish
popd
exit /b %SETUP_RC%

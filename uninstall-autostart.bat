@echo off
REM uninstall-autostart: quita el acceso de Startup (revierte install-autostart.bat).
REM No toca el daemon en curso; usa instant-stop.bat para frenarlo.
setlocal
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Instant Dictado.lnk"
if not exist "%LINK%" (
  echo Autostart no estaba instalado.
  exit /b 0
)
del "%LINK%"
if not exist "%LINK%" (
  echo Autostart quitado.
  exit /b 0
) else (
  echo ERROR: no se pudo borrar "%LINK%".
  exit /b 1
)

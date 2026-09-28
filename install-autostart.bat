@echo off
REM install-autostart: crea acceso en la carpeta Startup del usuario -> instant-run.bat (oculto).
REM Reversible: corre uninstall-autostart.bat o borra el acceso a mano.
REM NO levanta nada ahora; el daemon arrancara en el proximo login.
setlocal
set "TARGET=%~dp0instant-run.bat"
set "WORKDIR=%~dp0"
set "LINKDIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%LINKDIR%\Instant Dictado.lnk"
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut($env:LINK); $s.TargetPath=$env:TARGET; $s.WorkingDirectory=$env:WORKDIR; $s.Description='Instant dictado hold-to-talk (daemon oculto)'; $s.Save()"
if exist "%LINK%" (
  echo Autostart instalado: "%LINK%"
  echo El daemon arrancara oculto en el proximo login. Para quitarlo: uninstall-autostart.bat
  exit /b 0
) else (
  echo ERROR: no se pudo crear el acceso en Startup.
  exit /b 1
)

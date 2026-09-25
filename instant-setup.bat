@echo off
REM Abre el setup TUI (descarga modelos ~670MB, elige mic/tecla). Sin args -> `setup`.
set "EXE=C:\Users\juans\AppData\Roaming\Python\Python314\Scripts\instant.exe"
if exist "%EXE%" (
  if "%~1"=="" (
    "%EXE%" setup
  ) else (
    "%EXE%" %*
  )
) else (
  if "%~1"=="" (
    python -m instant_app setup
  ) else (
    python -m instant_app %*
  )
)

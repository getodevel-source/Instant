; Instalador de Instant para Windows: por usuario, sin admin, con desinstalador.
;
; Se compila desde el repo con Inno Setup 6:
;   iscc /DAppVersion=0.1.2 /DSourceDir=..\dist\Instant installer\instant.iss
; y el CI lo hace en cada tag. El asset se llama siempre `Instant-Setup.exe`
; (sin versión en el nombre) porque el actualizador de la app lo busca así.
;
; Al desinstalar se conservan a propósito la config (%APPDATA%\instant) y los
; modelos (%LOCALAPPDATA%\instant): borrar 670 MB de modelos y los ajustes por
; un update/desinstalación sería destructivo. Para purga total ver
; `scripts/uninstall.sh` (POSIX) o borrar esas carpetas a mano en Windows.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Instant"
#endif
#ifndef IconFile
  #define IconFile "..\dictado\build\instant.ico"
#endif

#define AppName "Instant"
#define AppExe "Instant.exe"
#define AppPublisher "getodevel-source"
#define AppURL "https://github.com/getodevel-source/Instant"

; LicenseFile solo si hay LICENSE en la raíz (el CI compila desde la raíz).
#if FileExists("..\\LICENSE") || FileExists("LICENSE")
#if FileExists("..\\LICENSE")
#define LicensePath "..\\LICENSE"
#else
#define LicensePath "LICENSE"
#endif
#endif

[Setup]
; AppId estable: las versiones nuevas actualizan esta instalación en el lugar.
AppId={{7C4B9E52-6F1A-4C0E-9C3D-2B7A5E8D1F44}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
AppCopyright=Copyright (c) 2026 {#AppPublisher} (MIT, ver LICENSE en el repo)
#ifdef LicensePath
LicenseFile={#LicensePath}
#endif
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
; Sin admin: todo vive bajo %LOCALAPPDATA% y el registro del usuario.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Instant-Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
; La app es de 64 bits (PySide6/sherpa-onnx): en ARM64 corre emulada.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
VersionInfoVersion={#AppVersion}.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "autostart"; Description: "Iniciar Instant con Windows (dictado en segundo plano)"; GroupDescription: "Inicio automático:"; Flags: unchecked
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
; Mismo nombre y destino que el arranque administrado por la app (autostart.py):
; así la casilla del panel y esta tarea no se pisan entre sí.
Name: "{userstartup}\Instant Dictado.lnk"; Filename: "{app}\{#AppExe}"; Parameters: "run"; WorkingDir: "{userdocs}"; Tasks: autostart

[Run]
; En /SILENT no se abre nada: el updater silencioso no puede robar el foco ni
; abrir ventanas al usuario (skipifsilent). En instalación interactiva sí se
; ofrece abrir el setup inicial (postinstall, desmarcable con "No volver" no
; aplica: es solo esta vez).
Filename: "{app}\{#AppExe}"; Description: "Abrir Instant ahora"; Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
; El daemon no tiene ventana: el Restart Manager no puede cerrarlo, así que
; se frena con el propio binario antes de borrar los archivos (evita restos).
Filename: "{app}\{#AppExe}"; Parameters: "stop"; RunOnceId: "StopInstantDaemon"
; Carrera: si el panel/daemon estaba *arrancando* cuando corrió el stop, el
; proceso aparece después y lockea los archivos. Se fuerza el cierre de
; cualquier cosa que quede corriendo desde {app}.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""Get-Process -Name Instant -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '{app}\*' }} | Stop-Process -Force"""; RunOnceId: "KillInstantProcesses"; Flags: runhidden

[UninstallDelete]
; La configuración y los modelos NO se tocan al desinstalar: viven en
; %APPDATA%\instant y %LOCALAPPDATA%\instant a propósito.
Type: dirifempty; Name: "{app}"

@echo off
setlocal
rem === Install FamilyCatalog into Revit 2024 (per-user add-ins) ===
rem Run build.cmd first.

set "SRC=%~dp0bin"
set "DST=%APPDATA%\Autodesk\Revit\Addins\2024"

if not exist "%SRC%\FamilyCatalog.addin" (
  echo [x] %SRC%\FamilyCatalog.addin not found - run build.cmd first
  exit /b 1
)

if not exist "%DST%" mkdir "%DST%"
if not exist "%DST%\FamilyCatalog" mkdir "%DST%\FamilyCatalog"

copy /y "%SRC%\FamilyCatalog.addin"          "%DST%\FamilyCatalog.addin"          >nul
copy /y "%SRC%\FamilyCatalog\FamilyCatalog.dll" "%DST%\FamilyCatalog\FamilyCatalog.dll" >nul
copy /y "%SRC%\FamilyCatalog\sync.png"       "%DST%\FamilyCatalog\sync.png"       >nul
copy /y "%SRC%\FamilyCatalog\load.png"       "%DST%\FamilyCatalog\load.png"       >nul

echo [ok] installed to: %DST%
echo     Restart Revit 2024. Появится вкладка "Каталог семейств".
endlocal

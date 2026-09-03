@echo off
setlocal
rem === Remove FamilyCatalog from Revit 2024 (per-user add-ins) ===
rem Revit must be CLOSED (FamilyCatalog.dll is locked while it runs).

set "DST=%APPDATA%\Autodesk\Revit\Addins\2024"

set "REMOVED="
if exist "%DST%\FamilyCatalog.addin" ( del /q "%DST%\FamilyCatalog.addin" & set "REMOVED=1" & echo [-] %DST%\FamilyCatalog.addin )
if exist "%DST%\FamilyCatalog"       ( rmdir /s /q "%DST%\FamilyCatalog"  & set "REMOVED=1" & echo [-] %DST%\FamilyCatalog\ )

rem settings (remembered catalog folder) — optional, ask
if exist "%APPDATA%\FamilyCatalog" (
  choice /m "Удалить и настройки (%APPDATA%\FamilyCatalog, запомненный путь к каталогу)"
  if not errorlevel 2 ( rmdir /s /q "%APPDATA%\FamilyCatalog" & echo [-] %APPDATA%\FamilyCatalog\ )
)

if defined REMOVED (
  echo [ok] FamilyCatalog удалён. Скрытые метки даты в .rvt остаются - они невидимы.
) else (
  echo [i] Ничего не найдено - плагин уже не установлен.
)
endlocal

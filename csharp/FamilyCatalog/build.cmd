@echo off
setlocal
rem === Build FamilyCatalog.dll with the .NET Framework C# compiler (no Visual Studio) ===

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
set "REVIT=C:\Program Files\Autodesk\Revit 2024"
set "FW=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319"
set "WPF=%FW%\WPF"
set "OUT=%~dp0bin"
set "PKG=%OUT%\FamilyCatalog"

if not exist "%CSC%" ( echo [x] csc.exe not found: %CSC% & exit /b 1 )
if not exist "%REVIT%\RevitAPI.dll" ( echo [x] RevitAPI.dll not found under: %REVIT% & exit /b 1 )

if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%PKG%"

"%CSC%" /nologo /utf8output /nowarn:618 /target:library /platform:anycpu /optimize+ /langversion:5 ^
 /out:"%PKG%\FamilyCatalog.dll" ^
 /reference:"%REVIT%\RevitAPI.dll" ^
 /reference:"%REVIT%\RevitAPIUI.dll" ^
 /reference:"%FW%\System.dll" ^
 /reference:"%FW%\System.Core.dll" ^
 /reference:"%FW%\System.Xml.dll" ^
 /reference:"%FW%\System.Windows.Forms.dll" ^
 /reference:"%FW%\System.Drawing.dll" ^
 /reference:"%WPF%\PresentationCore.dll" ^
 /reference:"%WPF%\PresentationFramework.dll" ^
 /reference:"%WPF%\WindowsBase.dll" ^
 /reference:"%FW%\System.Xaml.dll" ^
 "%~dp0Core.cs" "%~dp0Windows.cs" "%~dp0Commands.cs" "%~dp0App.cs"

if errorlevel 1 ( echo [x] BUILD FAILED & exit /b 1 )

copy /y "%~dp0sync.png" "%PKG%\sync.png" >nul
copy /y "%~dp0load.png" "%PKG%\load.png" >nul
copy /y "%~dp0FamilyCatalog.addin" "%OUT%\FamilyCatalog.addin" >nul

echo [ok] built:  %PKG%\FamilyCatalog.dll
echo [ok] package: %OUT%   (FamilyCatalog.addin + FamilyCatalog\)
endlocal

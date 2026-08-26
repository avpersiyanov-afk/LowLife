<#
.SYNOPSIS
    Регистрирует FamilyVersionStamp в Revit на этой машине: собирает DLL (если
    нужно) и кладёт .addin-манифест с правильным абсолютным путём в папку
    Addins нужной версии Revit.

.PARAMETER RevitVersion
    Версия Revit, под которую регистрировать аддин (папка Addins и, если
    приходится собирать, RevitAPI.dll берутся из "C:\Program Files\Autodesk\Revit <версия>").
    По умолчанию 2024.

.PARAMETER AllUsers
    Установить в %ProgramData% (для всех пользователей) вместо %APPDATA%
    (текущий пользователь). Требует прав администратора.

.EXAMPLE
    .\install.ps1
    .\install.ps1 -RevitVersion 2025
#>
param(
    [string]$RevitVersion = "2024",
    [switch]$AllUsers
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$dllPath = Join-Path $root "bin\Release\FamilyVersionStamp.dll"

if (-not (Test-Path $dllPath)) {
    Write-Host "DLL не найдена ($dllPath) - собираю..."
    $dotnet = Join-Path $env:USERPROFILE ".dotnet\dotnet.exe"
    if (-not (Test-Path $dotnet)) { $dotnet = "dotnet" }
    $revitInstallDir = "C:\Program Files\Autodesk\Revit $RevitVersion"
    & $dotnet build "$root\FamilyVersionStamp.csproj" -c Release "-p:RevitInstallDir=$revitInstallDir"
    if ($LASTEXITCODE -ne 0) { throw "Сборка не удалась." }
}

if (-not (Test-Path $dllPath)) {
    throw "После сборки DLL всё равно не найдена: $dllPath"
}

$addinTemplate = Join-Path $root "FamilyVersionStamp.addin"
[xml]$xml = Get-Content $addinTemplate -Encoding UTF8
$xml.SelectSingleNode("//Assembly").InnerText = $dllPath

$addinsRoot = if ($AllUsers) { $env:ProgramData } else { $env:APPDATA }
$targetDir = Join-Path $addinsRoot "Autodesk\Revit\Addins\$RevitVersion"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

$targetFile = Join-Path $targetDir "FamilyVersionStamp.addin"
$xml.Save($targetFile)

Write-Host "Готово: $targetFile"
Write-Host "  -> Assembly: $dllPath"
Write-Host "Перезапустите Revit $RevitVersion - команда появится в Надстройки -> Внешние инструменты."


# Run in the engineer's Windows session. No token is passed via command line.
# The server grant, not this installer or Windows login, enforces write scope.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$scriptUrl = Read-Host 'Адрес Apps Script с окончанием /exec'
if ($scriptUrl -notmatch '^https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec$') { throw 'Invalid URL' }
$secureToken = Read-Host 'Токен отдела' -AsSecureString
$tokenPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $modelToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPtr)
    # Verify scope before storing the encrypted credential.
    $body = @{action='connect';token=$modelToken} | ConvertTo-Json -Compress
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $response = Invoke-RestMethod -Method Post -Uri $scriptUrl -ContentType 'text/plain; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
    if (-not $response.ok) {
        if ($response.error -eq 'DEPARTMENT_REQUIRED') { throw 'У старого токена не указан отдел. Запросите новый токен отдела у администратора.' }
        throw 'Не удалось проверить токен. Проверьте адрес, токен и актуальность Apps Script.'
    }
    if ($response.credential_scope -ne 'group') { throw 'Для установки на все объекты нужен общий токен отдела.' }
    $discipline = [string]$response.department
    $disciplineRoles = @{'ОВиК'='VIS';'ВК'='VIS';'ЭОМ'='VIS';'СС'='VIS';'АК'='VIS';'КР'='KR';'АР'='AR'}
    if (-not $disciplineRoles.ContainsKey($discipline)) { throw 'Не удалось определить отдел по токену.' }
    $modelRole = $disciplineRoles[$discipline]
    if ($response.role -ne $modelRole) { throw 'Режим токена не соответствует отделу. Обратитесь к администратору.' }
    $protectedToken = [Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect(
        [Text.Encoding]::UTF8.GetBytes($modelToken), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser))
    # Same sorted compact JSON key as Python core.dumps.
    $connectionKey = [ordered]@{model='*';project='*';role=$modelRole} | ConvertTo-Json -Compress
    $configPath = Join-Path $env:APPDATA 'pyRevit\LowLifeOpeningJournal_connections.json'
    $configDir = Split-Path $configPath
    New-Item -ItemType Directory -Force $configDir | Out-Null
    $connections = @{}
    if (Test-Path $configPath) {
        $existing = Get-Content -Raw -Encoding UTF8 $configPath | ConvertFrom-Json
        $existing.PSObject.Properties | ForEach-Object { $connections[$_.Name] = $_.Value }
    }
    $connections[$connectionKey] = @{url=$scriptUrl;token_dpapi=$protectedToken;sheet_url=$response.sheet_url;discipline=$discipline}
    $configJson = $connections | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText($configPath, $configJson, (New-Object Text.UTF8Encoding($false)))
    Write-Host ('Подключён отдел ' + $discipline + '. Настройка действует для всех его объектов и моделей в этом профиле Windows.')
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPtr)
    $modelToken = $null
    $body = $null
    $secureToken.Dispose()
}

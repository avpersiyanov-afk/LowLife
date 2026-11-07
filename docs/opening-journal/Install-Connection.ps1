# Run in the engineer's Windows session. No token is passed via command line.
# The server grant, not this installer or Windows login, enforces write scope.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$projectCode = '__connection_check__'
$discipline = (Read-Host 'Дисциплина: ОК, ВК, ЭОМ, СС, АК, КР или АР').Trim().ToUpperInvariant()
$disciplineRoles = @{'ОК'='VIS';'ВК'='VIS';'ЭОМ'='VIS';'СС'='VIS';'АК'='VIS';'КР'='KR';'АР'='AR'}
if (-not $disciplineRoles.ContainsKey($discipline)) { throw 'Неизвестная дисциплина' }
$modelRole = $disciplineRoles[$discipline]
$modelUid = '__connection_check__'
$scriptUrl = Read-Host 'Apps Script /exec URL'
if ($scriptUrl -notmatch '^https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec$') { throw 'Invalid URL' }
$secureToken = Read-Host 'Shared group token' -AsSecureString
$tokenPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $modelToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPtr)
    # Verify scope before storing the encrypted credential.
    $body = @{action='status';token=$modelToken;project=$projectCode;role=$modelRole;model=$modelUid;discipline=$discipline} | ConvertTo-Json -Compress
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $response = Invoke-RestMethod -Method Post -Uri $scriptUrl -ContentType 'text/plain; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
    if (-not $response.ok -or $response.credential_scope -ne 'group') { throw 'A valid shared group token for the selected discipline is required' }
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
    Write-Host 'Group connection verified for all projects and models of the selected discipline in this Windows profile.'
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPtr)
    $modelToken = $null
    $body = $null
    $secureToken.Dispose()
}

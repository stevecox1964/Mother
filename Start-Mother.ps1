$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$port = if ($env:MOTHER_PORT) { $env:MOTHER_PORT } else { '5010' }
$url = "http://127.0.0.1:$port"
# Stop every Mother server from this folder so the new start loads current code.
# The venv python.exe starts a child with the same command line, so both match.
$serverCommand = "*$projectRoot\.venv\Scripts\python.exe*backend/run.py*"
$old = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like $serverCommand })
foreach ($process in $old) {
    Write-Host "Stopping old Mother process $($process.ProcessId)."
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}
foreach ($process in $old) {
    Wait-Process -Id $process.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
    if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
        throw "Could not stop old Mother process $($process.ProcessId)."
    }
}
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    throw "Port $port is still used by process $($listener.OwningProcess), which is not a Mother server from this folder. Stop it, or set MOTHER_PORT."
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & python -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $pythonPath -m pip install -r (Join-Path $projectRoot 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install backend dependencies.' }
Push-Location (Join-Path $projectRoot 'frontend')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Could not install frontend dependencies.' }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
$server = Start-Process -FilePath $pythonPath -ArgumentList 'backend/run.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'server.log') -RedirectStandardError (Join-Path $projectRoot 'server-error.log') -PassThru
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'data') | Out-Null
Set-Content -LiteralPath (Join-Path $projectRoot 'data\server.pid') -Value $server.Id
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1
        if ($health.name -eq 'Mother') {
            Start-Process $url
            Write-Host "Mother is running at $url (PID $($server.Id))."
            exit 0
        }
    } catch { }
    if ($server.HasExited) { throw 'Mother stopped. See server-error.log.' }
}
throw 'Mother did not become ready. See server-error.log.'

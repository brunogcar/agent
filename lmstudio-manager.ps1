$AgentPath = 'D:\mcp\agent'
$LMStudioExe = "$env:LOCALAPPDATA\Programs\LM Studio\LM Studio.exe"
$VenvActivate = Join-Path $AgentPath 'venv\Scripts\Activate.ps1'
$EnvFile = Join-Path $AgentPath '.env'

function Test-Lms {
    try { & lms version | Out-Null; return $true } catch { return $false }
}

function Get-LoadedModels {
    $output = & lms ps 2>$null
    $models = @()
    if ($output -match 'No models are currently loaded') { return $models }
    $lines = $output -split '\r?\n'
    foreach ($line in $lines) {
        if ($line -match '^IDENTIFIER|^---|^\s*$') { continue }
        $first = ($line -split '\s+')[0]
        if ($first -match '^[^:]+') { $models += $matches[0] }
    }
    return $models
}

function Read-EnvModels {
    $fallback = @('gemma-4-e2b-it-qat', 'gemma-2-2b-it', 'lfm2-1.2b-tool')
    if (-not (Test-Path $EnvFile)) {
        Write-Host '[WARN] .env not found -- using fallback' -ForegroundColor Yellow
        return $fallback
    }
    $models = @()
    $seen = @{}
    foreach ($line in Get-Content $EnvFile) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        if ($t -match '^([A-Z_]+_MODEL)\s*=\s*(.+)$') {
            $m = $matches[2].Trim()
            if ($m -and -not $seen[$m]) { $seen[$m] = $true; $models += $m }
        }
    }
    if ($models.Count -eq 0) { return $fallback }
    return $models
}

function Start-Daemon {
    Write-Host ''
    Write-Host '[DAEMON] Starting LM Studio daemon...' -ForegroundColor Yellow
    & lms daemon up | Out-Null
    Write-Host '[DAEMON] Ready' -ForegroundColor Green
}

function Load-Models {
    param([string[]]$Models)
    Start-Daemon
    $loaded = Get-LoadedModels
    $loadedCount = 0
    $skipCount = 0
    Write-Host ''
    Write-Host '[LOADING MODELS]' -ForegroundColor Yellow
    foreach ($model in $Models) {
        if ($loaded -contains $model) {
            Write-Host ('  [SKIP] ' + $model + ' already loaded') -ForegroundColor Magenta
            $skipCount++
        } else {
            Write-Host ('  [LOAD] ' + $model + ' ...') -ForegroundColor Yellow -NoNewline
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            & lms load $model --yes 2>$null | Out-Null
            $sw.Stop()
            $sec = [math]::Round($sw.Elapsed.TotalSeconds, 1)
            if ($LASTEXITCODE -eq 0) {
                Write-Host (' OK (' + $sec + 's)') -ForegroundColor Green
                $loadedCount++
            } else {
                Write-Host ' FAIL' -ForegroundColor Red
            }
        }
    }
    Write-Host ''
    Write-Host ('Loaded: ' + $loadedCount + ' | Skipped: ' + $skipCount + ' | Total: ' + $Models.Count) -ForegroundColor Cyan
}

function Unload-AllModels {
    $models = Get-LoadedModels
    if ($models.Count -eq 0) {
        Write-Host ''
        Write-Host '[INFO] No models currently loaded.' -ForegroundColor Gray
        return
    }
    Write-Host ''
    Write-Host '[UNLOADING]' -ForegroundColor Yellow
    foreach ($model in $models) {
        Write-Host ('  Unloading ' + $model + ' ...') -ForegroundColor Yellow -NoNewline
        & lms unload $model 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Host ' OK' -ForegroundColor Green }
        else { Write-Host ' FAIL' -ForegroundColor Red }
    }
}

function Start-LMStudioGUI {
    if (Test-Path $LMStudioExe) {
        Write-Host ''
        Write-Host '[GUI] Launching LM Studio...' -ForegroundColor Yellow
        Start-Process $LMStudioExe
        Write-Host '[GUI] Done' -ForegroundColor Green
    } else {
        Write-Host ''
        Write-Host ('[GUI] Not found at: ' + $LMStudioExe) -ForegroundColor Red
    }
}

function Start-LMStudioServer {
    Write-Host ''
    Write-Host '[SERVER] Starting LM Studio API server...' -ForegroundColor Yellow
    & lms server start 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host '[SERVER] Running' -ForegroundColor Green }
    else { Write-Host '[SERVER] Already running or failed' -ForegroundColor Gray }
}

function Stop-LMStudioServer {
    Write-Host ''
    Write-Host '[SERVER] Stopping LM Studio API server...' -ForegroundColor Yellow
    & lms server stop 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host '[SERVER] Stopped' -ForegroundColor Green }
    else { Write-Host '[SERVER] Not running' -ForegroundColor Gray }
}

function Open-AgentTerminal {
    Write-Host ''
    Write-Host '[TERMINAL] Opening new agent terminal...' -ForegroundColor Yellow
    $cmd = ('& "' + $VenvActivate + '"; Set-Location "' + $AgentPath + '"; Write-Host "Agent venv activated" -ForegroundColor Green')
    Start-Process powershell.exe -ArgumentList '-NoExit', '-Command', $cmd
}

function Run-Gateway {
    Write-Host ''
    Write-Host '[GATEWAY] Starting gateway in new window...' -ForegroundColor Yellow
    $cmd = ('& "' + $VenvActivate + '"; Set-Location "' + $AgentPath + '"; python core/gateway.py')
    Start-Process powershell.exe -ArgumentList '-NoExit', '-Command', $cmd
}

function Full-Startup {
    $models = Read-EnvModels
    Load-Models -Models $models
    Start-LMStudioServer
    Start-LMStudioGUI
    Write-Host ''
    Write-Host '[OK] Full startup complete!' -ForegroundColor Green
}

function Full-Shutdown {
    Unload-AllModels
    Stop-LMStudioServer
    Write-Host ''
    Write-Host '[OK] Shutdown complete!' -ForegroundColor Green
}

function Show-Menu {
    Clear-Host
    $loaded = Get-LoadedModels
    $status = if ($loaded.Count -gt 0) { ($loaded -join ', ') } else { 'none' }
    $envModels = Read-EnvModels
    $envList = if ($envModels.Count -gt 0) { ($envModels -join ', ') } else { 'fallback' }
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host '     LM STUDIO + AGENT MANAGER' -ForegroundColor Cyan
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host ('Agent Path: ' + $AgentPath) -ForegroundColor DarkGray
    Write-Host ('Loaded:     ' + $status) -ForegroundColor DarkGray
    Write-Host ('From .env:  ' + $envList) -ForegroundColor DarkGray
    Write-Host '----------------------------------------' -ForegroundColor DarkGray
    Write-Host ''
    Write-Host '  1. Full Startup (daemon + .env models + server + GUI)' -ForegroundColor White
    Write-Host '  2. Load Models from .env' -ForegroundColor White
    Write-Host '  3. Unload All Models' -ForegroundColor White
    Write-Host '  4. Start LM Studio GUI' -ForegroundColor White
    Write-Host '  5. Start API Server' -ForegroundColor White
    Write-Host '  6. Stop API Server' -ForegroundColor White
    Write-Host '  7. Open Agent Terminal (venv activated)' -ForegroundColor White
    Write-Host '  8. Run Gateway (new window)' -ForegroundColor White
    Write-Host '  9. Full Shutdown (unload + stop server)' -ForegroundColor White
    Write-Host ''
    Write-Host '  0. Exit' -ForegroundColor Red
    Write-Host ''
    Write-Host '----------------------------------------' -ForegroundColor DarkGray
}

if (-not (Test-Lms)) {
    Write-Host 'ERROR: lms CLI not found. Is LM Studio installed?' -ForegroundColor Red
    exit 1
}

do {
    Show-Menu
    $choice = Read-Host 'Select option'
    switch ($choice) {
        '1' { Full-Startup }
        '2' { Load-Models -Models (Read-EnvModels) }
        '3' { Unload-AllModels }
        '4' { Start-LMStudioGUI }
        '5' { Start-LMStudioServer }
        '6' { Stop-LMStudioServer }
        '7' { Open-AgentTerminal }
        '8' { Run-Gateway }
        '9' { Full-Shutdown }
        '0' { Write-Host ''; Write-Host 'Goodbye!' -ForegroundColor Green; exit 0 }
        default { Write-Host ''; Write-Host 'Invalid option' -ForegroundColor Red }
    }
    Write-Host ''
    if ($choice -ne '0') {
        Read-Host 'Press Enter to continue'
    }
} until ($choice -eq '0')

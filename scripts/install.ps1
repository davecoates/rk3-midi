param(
    [string]$SourceDir = $PSScriptRoot,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$taskName = "rk3-midi"
$sourceRoot = (Resolve-Path -LiteralPath $SourceDir).Path
$cliSource = Join-Path $sourceRoot "rk3-midi.exe"
$backgroundSource = Join-Path $sourceRoot "background\rk3-midi-background.exe"
$configSource = Join-Path $sourceRoot "config.example.toml"
foreach ($required in @($cliSource, $backgroundSource, $configSource)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing release file: $required" }
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\rk3-midi"
$configDir = Join-Path $env:APPDATA "rk3-midi"
$configPath = Join-Path $configDir "config.toml"
$runtimeDir = Join-Path $env:LOCALAPPDATA "rk3-midi"
$stopRequest = Join-Path $runtimeDir "stop.request"
$backgroundPaths = @(
    (Join-Path $installDir "rk3-midi-background.exe"),
    (Join-Path $installDir "background\rk3-midi-background.exe")
)

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
    New-Item -ItemType File -Force -Path $stopRequest | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    do {
        $running = @(Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -in $backgroundPaths
        })
        if ($running.Count -eq 0) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
}
Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -in $backgroundPaths
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $stopRequest -Force -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force -Path $installDir, $configDir | Out-Null
Copy-Item -LiteralPath $cliSource -Destination $installDir -Force
Copy-Item -LiteralPath (Split-Path -Parent $backgroundSource) `
    -Destination $installDir -Recurse -Force
Copy-Item -LiteralPath $configSource -Destination $installDir -Force
Remove-Item -LiteralPath (Join-Path $installDir "rk3-midi-background.exe") `
    -Force -ErrorAction SilentlyContinue
if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath $configSource -Destination $configPath
    Write-Output "Created config: $configPath"
} else {
    Write-Output "Preserved existing config: $configPath"
}

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$backgroundExe = Join-Path $installDir "background\rk3-midi-background.exe"
$action = New-ScheduledTaskAction -Execute $backgroundExe -WorkingDirectory $installDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Native Instruments Rig Kontrol 3 to loopMIDI relay" `
    -Force | Out-Null

if (-not $NoStart) {
    Start-ScheduledTask -TaskName $taskName
}

Write-Output "Installed to: $installDir"
Write-Output "Scheduled Task: $taskName"
Write-Output "CLI: $installDir\rk3-midi.exe"
Write-Output "Log: $env:LOCALAPPDATA\rk3-midi\rk3-midi.log"
Write-Output "Ensure loopMIDI is configured to start automatically at logon."

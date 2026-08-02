param(
    [switch]$RemoveUserData
)

$ErrorActionPreference = "Stop"
$taskName = "rk3-midi"
$installDir = Join-Path $env:LOCALAPPDATA "Programs\rk3-midi"
$configDir = Join-Path $env:APPDATA "rk3-midi"

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -eq (Join-Path $installDir "rk3-midi-background.exe")
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $installDir) {
    $resolvedInstall = (Resolve-Path -LiteralPath $installDir).Path
    $expectedParent = (Resolve-Path -LiteralPath (Join-Path $env:LOCALAPPDATA "Programs")).Path
    if ($resolvedInstall -ne (Join-Path $expectedParent "rk3-midi")) {
        throw "Refusing to remove unexpected install path: $resolvedInstall"
    }
    Remove-Item -LiteralPath $resolvedInstall -Recurse -Force
}

if ($RemoveUserData -and (Test-Path -LiteralPath $configDir)) {
    $resolvedConfig = (Resolve-Path -LiteralPath $configDir).Path
    $expectedConfig = Join-Path (Resolve-Path -LiteralPath $env:APPDATA).Path "rk3-midi"
    if ($resolvedConfig -ne $expectedConfig) {
        throw "Refusing to remove unexpected config path: $resolvedConfig"
    }
    Remove-Item -LiteralPath $resolvedConfig -Recurse -Force
    Write-Output "Removed user config and calibration: $resolvedConfig"
} else {
    Write-Output "Preserved user config and calibration: $configDir"
}
Write-Output "rk3-midi uninstalled. WinUSB and loopMIDI were not changed."

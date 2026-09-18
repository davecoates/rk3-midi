param(
    [string]$Version = "0.4.1"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Virtual environment not found at $pythonExe"
}

& $pythonExe -m pip install --no-build-isolation -e "$projectRoot[dev]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }

$binaryDir = Join-Path $projectRoot "dist"
$workRoot = Join-Path $projectRoot "build\pyinstaller"
$specDir = Join-Path $workRoot "spec"
$versionFile = Join-Path $projectRoot "packaging\version_info.txt"
$common = @(
    "--noconfirm", "--clean", "--noupx",
    "--distpath", $binaryDir,
    "--specpath", $specDir,
    "--paths", (Join-Path $projectRoot "src"),
    "--collect-all", "libusb_package",
    "--hidden-import", "usb.backend.libusb1",
    "--version-file", $versionFile
)

& $pythonExe -m PyInstaller @common `
    "--onefile" `
    "--console" `
    "--name" "rk3-midi" `
    "--workpath" (Join-Path $workRoot "cli") `
    (Join-Path $projectRoot "packaging\rk3_midi_cli.py")
if ($LASTEXITCODE -ne 0) { throw "CLI executable build failed" }

& $pythonExe -m PyInstaller @common `
    "--onedir" `
    "--windowed" `
    "--name" "rk3-midi-background" `
    "--workpath" (Join-Path $workRoot "background") `
    (Join-Path $projectRoot "packaging\rk3_midi_background.py")
if ($LASTEXITCODE -ne 0) { throw "Background executable build failed" }

$releaseRoot = Join-Path $projectRoot "release"
New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
$releaseDir = Join-Path $releaseRoot "rk3-midi-$Version-windows-x64"
if (Test-Path -LiteralPath $releaseDir) {
    $resolvedRelease = (Resolve-Path -LiteralPath $releaseDir).Path
    $resolvedRoot = (Resolve-Path -LiteralPath $releaseRoot).Path
    if (-not $resolvedRelease.StartsWith($resolvedRoot + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove unexpected release path: $resolvedRelease"
    }
    Remove-Item -LiteralPath $resolvedRelease -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseDir | Out-Null

Copy-Item -LiteralPath (Join-Path $binaryDir "rk3-midi.exe") -Destination $releaseDir
Copy-Item -LiteralPath (Join-Path $binaryDir "rk3-midi-background") `
    -Destination (Join-Path $releaseDir "background") -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot "config.example.toml") -Destination $releaseDir
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $releaseDir
$releaseDocs = Join-Path $releaseDir "docs"
New-Item -ItemType Directory -Path $releaseDocs | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "docs\PROTOCOL.md") -Destination $releaseDocs
Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\install.ps1") -Destination $releaseDir
Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\uninstall.ps1") -Destination $releaseDir

$hashLines = Get-ChildItem -LiteralPath $releaseDir -File -Recurse |
    Where-Object Name -ne "SHA256SUMS.txt" |
    ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    $relative = [IO.Path]::GetRelativePath($releaseDir, $_.FullName)
    "$($hash.Hash.ToLowerInvariant())  $relative"
}
$hashLines | Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") -Encoding ascii

$zipPath = "$releaseDir.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $releaseDir -DestinationPath $zipPath -CompressionLevel Optimal
Write-Output "Release created: $zipPath"

# Skill Tree — Electron desktop shell setup.
#
# Run from the electron/ folder with the skill-tree conda env active (so npm/node
# are the env's). Installs the npm dependencies and works around a broken Electron
# unzip step in this environment (see setup.md) by extracting the binary manually.
#
#   conda activate skill-tree
#   cd "C:\Users\jonah\Documents\Code\Skill Tree\electron"
#   .\setup.ps1

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Push-Location $root
try {
    Write-Host "Installing npm dependencies..."
    npm install

    $elDir = Join-Path $root 'node_modules\electron'
    $exe   = Join-Path $elDir 'dist\electron.exe'

    if (-not (Test-Path $exe)) {
        Write-Host "Electron binary missing - extracting it manually..."
        $ver     = (Get-Content (Join-Path $elDir 'package.json') -Raw | ConvertFrom-Json).version
        $zipName = "electron-v$ver-win32-x64.zip"

        # Prefer the zip @electron/get already cached during npm install.
        $zip = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'electron\Cache') -Recurse -Filter $zipName -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $zip) {
            $url = "https://github.com/electron/electron/releases/download/v$ver/$zipName"
            $tmp = Join-Path $env:TEMP $zipName
            Write-Host "Downloading $url ..."
            Invoke-WebRequest -Uri $url -OutFile $tmp
            $zip = Get-Item $tmp
        }

        $dist = Join-Path $elDir 'dist'
        Remove-Item $dist -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force $dist | Out-Null
        Expand-Archive -Path $zip.FullName -DestinationPath $dist -Force
        Set-Content -Path (Join-Path $elDir 'path.txt') -Value 'electron.exe' -NoNewline
    }

    if (Test-Path $exe) {
        Write-Host "Electron ready: $exe"
    } else {
        throw "Electron setup failed: $exe still missing."
    }
} finally {
    Pop-Location
}

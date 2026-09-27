param(
    [Parameter(Mandatory = $true)]
    [string]$Installer
)

$ErrorActionPreference = 'Stop'
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$setup = Start-Process -FilePath $installerPath -ArgumentList '/S', '/CURRENTUSER' -WindowStyle Hidden -Wait -PassThru
if ($setup.ExitCode -ne 0) {
    throw "Windows installer exited with code $($setup.ExitCode)"
}

$app = Join-Path $env:LOCALAPPDATA 'Programs\Skill Tree\Skill Tree.exe'
$startLink = Join-Path ([Environment]::GetFolderPath('Programs')) 'Skill Tree.lnk'
$desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Skill Tree.lnk'
$uninstaller = Join-Path $env:LOCALAPPDATA 'Programs\Skill Tree\Uninstall Skill Tree.exe'

foreach ($path in @($app, $startLink, $desktopLink, $uninstaller)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Windows installer did not create $path"
    }
}

$shell = New-Object -ComObject WScript.Shell
foreach ($link in @($startLink, $desktopLink)) {
    $target = $shell.CreateShortcut($link).TargetPath
    if ($target -ne $app) {
        throw "Shortcut $link points to $target instead of $app"
    }
}

Write-Output "Installed app and both shortcuts point to $app"

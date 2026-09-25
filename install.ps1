$ErrorActionPreference = 'Stop'
$installPath = Join-Path $env:LOCALAPPDATA 'JxnuCampusAutoLogin'
New-Item -ItemType Directory -Path $installPath -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'artifacts') -File | Where-Object Extension -ne '.pdb' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $installPath -Force
}
$exePath = Join-Path $installPath 'CampusAutoLogin.exe'
$runPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if (-not (Test-Path -LiteralPath $runPath)) { New-Item -Path $runPath | Out-Null }
Set-ItemProperty -LiteralPath $runPath -Name 'JxnuCampusAutoLogin' -Value ('"' + $exePath + '" --background')
$desktopPath = Join-Path ([Environment]::GetFolderPath('Desktop')) '江西师大校园网.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($desktopPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $installPath
$shortcut.Description = '江西师范大学移动校园网自动登录'
$shortcut.Save()
Start-Process -FilePath $exePath -WorkingDirectory $installPath
Write-Output ('Installed: ' + $exePath)
Write-Output 'Auto-start registered for the current Windows user.'

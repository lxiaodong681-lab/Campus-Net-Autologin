$ErrorActionPreference = 'Stop'
$installPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'JxnuCampusAutoLogin'
New-Item -ItemType Directory -Path $installPath -Force | Out-Null
$dataPath = Join-Path $installPath 'data'
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
$oldSettings = Join-Path $env:LOCALAPPDATA 'JxnuCampusAutoLogin\settings.json'
$newSettings = Join-Path $dataPath 'settings.json'
if ((Test-Path -LiteralPath $oldSettings) -and -not (Test-Path -LiteralPath $newSettings)) {
    Copy-Item -LiteralPath $oldSettings -Destination $newSettings
}
Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'artifacts') -File | Where-Object Extension -ne '.pdb' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $installPath -Force
}
$exePath = Join-Path $installPath 'CampusAutoLogin.exe'
$registration = Start-Process -FilePath $exePath -ArgumentList '--register-startup' -WindowStyle Hidden -PassThru
if (-not $registration.WaitForExit(30000)) { Stop-Process -Id $registration.Id; throw 'Startup registration timed out' }
if ($registration.ExitCode -ne 0) { throw 'Startup registration failed' }
$desktopPath = Join-Path ([Environment]::GetFolderPath('Desktop')) '江西师大校园网.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($desktopPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $installPath
$shortcut.Description = '江西师范大学移动校园网自动登录'
$shortcut.Save()
$service = New-Object -ComObject Schedule.Service
$service.Connect()
$taskName = 'JxnuCampusAutoLogin-' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$service.GetFolder('\').GetTask($taskName).Run($null) | Out-Null
Write-Output ('Installed: ' + $exePath)
Write-Output 'Windows logon task registered and started for the current user. Open the desktop shortcut for settings.'

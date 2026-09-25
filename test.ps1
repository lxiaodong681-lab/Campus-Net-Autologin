param([string]$DotnetPath = 'dotnet', [switch]$Live)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $testArgs = @('run', '--project', 'tests/Tests.csproj', '--configuration', 'Release')
    if ($Live) { $testArgs += @('--', '--live') }
    & $DotnetPath @testArgs
    if ($LASTEXITCODE -ne 0) { throw '测试失败' }
} finally { Pop-Location }

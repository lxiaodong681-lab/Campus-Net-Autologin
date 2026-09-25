param([string]$DotnetPath = 'dotnet')
$ErrorActionPreference = 'Stop'
& $DotnetPath publish (Join-Path $PSScriptRoot 'src\CampusAutoLogin.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -o (Join-Path $PSScriptRoot 'artifacts')
if ($LASTEXITCODE -ne 0) { throw '编译失败，请确认已安装 .NET 8 SDK 且可以访问 NuGet。' }

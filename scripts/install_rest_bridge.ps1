[CmdletBinding()]
param(
    [ValidateSet("Release", "Debug")]
    [string]$Configuration = "Release",
    [string]$RevitVersion = "2025",
    [ValidateSet("Primary", "Secondary")]
    [string]$BridgeChannel = "Primary"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$bridgeRoot = Join-Path $repositoryRoot "RccBoq.RestBridge"
$buildPropsPath = Join-Path $bridgeRoot "Directory.Build.props"
[xml]$buildProps = Get-Content -LiteralPath $buildPropsPath -Raw
$bridgeVersion = [string]$buildProps.Project.PropertyGroup.Version
if ($bridgeVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "Bridge version is not valid semantic versioning: $bridgeVersion"
}
$revitProject = Join-Path $bridgeRoot "src\RccBoq.RestRevit\RccBoq.RestRevit.csproj"
$gatewayProject = Join-Path $bridgeRoot "src\RccBoq.RestGateway\RccBoq.RestGateway.csproj"
$mcpProject = Join-Path $bridgeRoot "src\RccBoq.RestMcp\RccBoq.RestMcp.csproj"
$templatePath = Join-Path $bridgeRoot "RccBoq.RestBridge.addin.template"
$channelSuffix = if ($BridgeChannel -eq "Secondary") { "-secondary" } else { "" }
$installRoot = Join-Path $env:LOCALAPPDATA "RCC_BOQ\RestBridge\v$bridgeVersion$channelSuffix"
$gatewayRoot = Join-Path $installRoot "Gateway"
$mcpRoot = Join-Path $installRoot "Mcp"
$manifestRoot = Join-Path $env:APPDATA "Autodesk\Revit\Addins\$RevitVersion"
$manifestPath = Join-Path $manifestRoot "RccBoq.RestBridge.addin"

if (-not (Test-Path -LiteralPath $revitProject)) {
    throw "Revit bridge project was not found: $revitProject"
}

dotnet build $revitProject --configuration $Configuration "-p:BridgeChannel=$BridgeChannel"
if ($LASTEXITCODE -ne 0) {
    throw "Revit bridge build failed."
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
New-Item -ItemType Directory -Path $gatewayRoot -Force | Out-Null
New-Item -ItemType Directory -Path $mcpRoot -Force | Out-Null
New-Item -ItemType Directory -Path $manifestRoot -Force | Out-Null

$revitOutput = Join-Path $bridgeRoot "src\RccBoq.RestRevit\bin\$Configuration\net8.0-windows"
Copy-Item -LiteralPath (Join-Path $revitOutput "RccBoq.RestRevit.dll") -Destination $installRoot -Force
Copy-Item -LiteralPath (Join-Path $revitOutput "RccBoq.RestCore.dll") -Destination $installRoot -Force

dotnet publish $gatewayProject --configuration $Configuration --runtime win-x64 `
    --self-contained false --output $gatewayRoot "-p:BridgeChannel=$BridgeChannel"
if ($LASTEXITCODE -ne 0) {
    throw "REST Gateway publish failed."
}

dotnet publish $mcpProject --configuration $Configuration --runtime win-x64 `
    --self-contained false --output $mcpRoot "-p:BridgeChannel=$BridgeChannel"
if ($LASTEXITCODE -ne 0) {
    throw "MCP server publish failed."
}

$assemblyPath = Join-Path $installRoot "RccBoq.RestRevit.dll"
$manifest = (Get-Content -LiteralPath $templatePath -Raw).Replace(
    "__ASSEMBLY_PATH__",
    $assemblyPath)
Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding UTF8

Write-Output "Installed RCC BOQ REST Bridge v$bridgeVersion ($BridgeChannel channel)"
Write-Output "Manifest: $manifestPath"
Write-Output "Assembly: $assemblyPath"
Write-Output "MCP server: $(Join-Path $mcpRoot 'RccBoq.RestMcp.exe')"
if ($BridgeChannel -eq "Primary") {
    Write-Output "Register it with Codex after installation:"
    Write-Output "  codex mcp add rcc-boq-v2 -- `"$(Join-Path $mcpRoot 'RccBoq.RestMcp.exe')`""
} else {
    Write-Output "Secondary endpoint: http://127.0.0.1:48886/rcc-boq"
    Write-Warning "The Revit manifest now targets Secondary. Restore Primary immediately after the test Revit has started."
}
Write-Output "Restart Revit 2025 before running live endpoint checks."

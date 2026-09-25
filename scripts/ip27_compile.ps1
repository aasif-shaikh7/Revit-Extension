# Compile - without running - every Python file the BOQ button loads, on
# pyRevit's own IronPython 2.7.12 engine, outside Revit.
#
# The regression harness compiles files with CPython 3, which accepts
# Python-3-only syntax that IronPython 2.7 rejects, and a file that
# IronPython cannot read stops the BOQ button from loading at all. This
# catches both an unterminated string and Python-3-only syntax.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ip27_compile.ps1
# Exit code: 0 when every file compiles, 1 otherwise.

$engineDir = Join-Path $env:APPDATA "pyRevit-Master\bin\netfx\engines\IPY2712PR"
if (-not (Test-Path $engineDir)) {
    Write-Output "pyRevit IronPython 2.7.12 engine not found at $engineDir"
    exit 1
}
foreach ($dll in @("pyRevitLabs.Microsoft.Scripting.dll", "pyRevitLabs.Microsoft.Dynamic.dll",
                   "pyRevitLabs.IronPython.dll", "pyRevitLabs.IronPython.Modules.dll")) {
    Add-Type -Path (Join-Path $engineDir $dll)
}
$engine = [IronPython.Hosting.Python]::CreateEngine()

$extension = Join-Path (Split-Path -Parent $PSScriptRoot) "Nudge.extension"
$files = @(Join-Path $extension "Nudge.tab\Generate.panel\BOQ.pushbutton\script.py")
$files += Get-ChildItem (Join-Path $extension "lib\*.py") | ForEach-Object { $_.FullName }

$failed = 0
foreach ($file in $files) {
    try {
        $null = $engine.CreateScriptSourceFromFile($file).Compile()
    } catch {
        $failed++
        $reason = $_.Exception.Message
        if ($_.Exception.InnerException) { $reason = $_.Exception.InnerException.Message }
        Write-Output ("FAILS on IronPython {0}: {1} - {2}" -f $engine.LanguageVersion, (Split-Path $file -Leaf), $reason)
    }
}
Write-Output ("IronPython {0}: {1} files compiled, {2} failed" -f $engine.LanguageVersion, $files.Count, $failed)
if ($failed) { exit 1 }
exit 0

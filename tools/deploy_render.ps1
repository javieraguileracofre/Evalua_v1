# Dispara deploy manual a Render (Windows / PowerShell).
# Requiere RENDER_DEPLOY_HOOK_URL en .env o variable de entorno.
param(
    [string]$HookUrl = $env:RENDER_DEPLOY_HOOK_URL,
    [switch]$ClearCache
)

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$argsList = @()
if ($HookUrl) { $argsList += @("--hook-url", $HookUrl) }
if ($ClearCache) { $argsList += "--clear-cache" }

python tools/deploy_render.py @argsList
exit $LASTEXITCODE

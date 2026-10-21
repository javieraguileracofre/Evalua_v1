#Requires -Version 5.1
<#
.SYNOPSIS
    Crea el acceso directo "Iniciar Aplicacion" en el escritorio del usuario actual.
.PARAMETER IconPath
    Ruta opcional a un .ico personalizado. Si se omite, se usa launcher\app.ico
    (si existe) o el icono de Python del entorno virtual.
#>
[CmdletBinding()]
param(
    [string]$IconPath = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

function New-UserShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$LinkPath,
        [Parameter(Mandatory = $true)][string]$VbsPath,
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][string]$IconLocation
    )
    $w = New-Object -ComObject WScript.Shell
    $s = $w.CreateShortcut($LinkPath)
    $s.TargetPath = Join-Path $env:SystemRoot "System32\wscript.exe"
    $s.Arguments = '"{0}"' -f $VbsPath
    $s.WorkingDirectory = Get-ProjectRoot
    $s.WindowStyle = 7
    $s.Description = $Description
    $s.IconLocation = $IconLocation
    $s.Save()
}

try {
    $desktop = [Environment]::GetFolderPath("Desktop")
    if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop)) {
        throw "No se pudo localizar la carpeta del escritorio del usuario."
    }

    $startVbs = Join-Path $PSScriptRoot "run_hidden.vbs"
    $stopVbs = Join-Path $PSScriptRoot "stop_hidden.vbs"
    if (-not (Test-Path -LiteralPath $startVbs)) {
        throw "Falta run_hidden.vbs en $PSScriptRoot"
    }

    $icon = $IconPath
    if ([string]::IsNullOrWhiteSpace($icon)) {
        $icon = Get-PreferredIconPath
    } elseif (-not (Test-Path -LiteralPath $icon)) {
        throw "No existe el icono indicado: $icon"
    }
    if ($icon.ToLowerInvariant().EndsWith(".ico") -or $icon.ToLowerInvariant().EndsWith(".exe")) {
        $iconLocation = "{0},0" -f $icon
    } else {
        $iconLocation = $icon
    }

    $startLnk = Join-Path $desktop "Iniciar Aplicación.lnk"
    New-UserShortcut -LinkPath $startLnk -VbsPath $startVbs -Description "Inicia EvaluaERP en localhost y abre el navegador" -IconLocation $iconLocation

    $stopLnk = $null
    if (Test-Path -LiteralPath $stopVbs) {
        $stopLnk = Join-Path $desktop "Detener Aplicación.lnk"
        New-UserShortcut -LinkPath $stopLnk -VbsPath $stopVbs -Description "Detiene EvaluaERP en localhost" -IconLocation $iconLocation
    }

    $msg = "Acceso directo creado en el escritorio:`r`n$startLnk"
    if ($stopLnk) {
        $msg += "`r`n`r`nTambien se creo:`r`n$stopLnk"
    }
    $msg += "`r`n`r`nDoble clic en 'Iniciar Aplicacion' para abrir EvaluaERP."
    Write-AppLog $msg
    Show-AppDialog -Message $msg -Kind "Info"
    Write-Host $msg
    exit 0
}
catch {
    $text = $_.Exception.Message
    Write-AppLog $text -Level "ERROR"
    Show-AppDialog -Message $text -Kind "Error"
    exit 1
}

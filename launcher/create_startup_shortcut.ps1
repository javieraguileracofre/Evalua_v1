#Requires -Version 5.1
<#
.SYNOPSIS
    Activa o quita el arranque automatico de EvaluaERP al iniciar sesion.
.PARAMETER Remove
    Si se indica, elimina el acceso de inicio automatico (no detiene la app si ya corre).
.PARAMETER IconPath
    Ruta opcional a un .ico personalizado.
#>
[CmdletBinding()]
param(
    [switch]$Remove,
    [string]$IconPath = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

try {
    $startup = [Environment]::GetFolderPath("Startup")
    if ([string]::IsNullOrWhiteSpace($startup) -or -not (Test-Path -LiteralPath $startup)) {
        # Fallback clasico por si el Known Folder no responde.
        $startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    }
    if (-not (Test-Path -LiteralPath $startup)) {
        throw "No se encontro la carpeta de inicio de Windows del usuario."
    }

    $lnk = Join-Path $startup "Iniciar Aplicación.lnk"

    if ($Remove) {
        if (Test-Path -LiteralPath $lnk) {
            Remove-Item -LiteralPath $lnk -Force
            $msg = "Inicio automatico desactivado.`r`nSe elimino:`r`n$lnk"
        } else {
            $msg = "No habia inicio automatico que quitar."
        }
        Write-AppLog $msg
        Show-AppDialog -Message $msg -Kind "Info"
        exit 0
    }

    $vbs = Join-Path $PSScriptRoot "run_hidden.vbs"
    if (-not (Test-Path -LiteralPath $vbs)) {
        throw "Falta run_hidden.vbs en $PSScriptRoot"
    }

    $icon = $IconPath
    if ([string]::IsNullOrWhiteSpace($icon)) {
        $icon = Get-PreferredIconPath
    } elseif (-not (Test-Path -LiteralPath $icon)) {
        throw "No existe el icono indicado: $icon"
    }
    $iconLocation = "{0},0" -f $icon

    $w = New-Object -ComObject WScript.Shell
    $s = $w.CreateShortcut($lnk)
    $s.TargetPath = Join-Path $env:SystemRoot "System32\wscript.exe"
    $s.Arguments = '"{0}"' -f $vbs
    $s.WorkingDirectory = Get-ProjectRoot
    $s.WindowStyle = 7
    $s.Description = "Inicia EvaluaERP al iniciar sesion (opcional)"
    $s.IconLocation = $iconLocation
    $s.Save()

    $msg = "Inicio automatico activado para este usuario de Windows.`r`n$lnk`r`n`r`nPara desactivarlo ejecute:`r`nlauncher\create_startup_shortcut.ps1 -Remove"
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

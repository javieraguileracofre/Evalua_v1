#Requires -Version 5.1
<#
.SYNOPSIS
    Detiene EvaluaERP si esta corriendo en el puerto local configurado.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

Set-Location -LiteralPath (Get-ProjectRoot)

try {
    $port = Get-AppPort
    Write-AppLog "=== Detener EvaluaERP (puerto $port) ==="

    $stopped = $false
    $savedPid = Get-SavedPid
    if ($savedPid) {
        Write-AppLog "Deteniendo arbol de proceso guardado PID $savedPid"
        Stop-ProcessTree -ProcessId $savedPid
        $stopped = $true
    }

    $listenPid = Get-ListeningPid -Port $port
    if ($listenPid) {
        if (Test-IsOurAppProcess -ProcessId $listenPid) {
            Write-AppLog "El puerto $port seguia en uso por nuestra app (PID $listenPid). Deteniendo."
            Stop-ProcessTree -ProcessId $listenPid
            $stopped = $true
        } else {
            $cmd = Get-ProcessCommandLine -ProcessId $listenPid
            $msg = "El puerto $port esta ocupado por otro programa (PID $listenPid), no se detuvo."
            if ($cmd) { $msg += "`r`n$cmd" }
            Write-AppLog $msg -Level "WARN"
            Show-AppDialog -Message $msg -Kind "Warning"
            exit 1
        }
    }

    Clear-PidFile

    # Segunda pasada breve por si uvicorn --reload dejo un hijo.
    Start-Sleep -Milliseconds 400
    $again = Get-ListeningPid -Port $port
    if ($again -and (Test-IsOurAppProcess -ProcessId $again)) {
        Stop-ProcessTree -ProcessId $again
        $stopped = $true
    }

    if ($stopped) {
        Write-AppLog "Aplicacion detenida."
        Show-AppDialog -Message "EvaluaERP se detuvo correctamente." -Kind "Info"
        exit 0
    }

    Write-AppLog "No habia ninguna instancia en ejecucion."
    Show-AppDialog -Message "EvaluaERP no estaba en ejecucion." -Kind "Info"
    exit 0
}
catch {
    $text = $_.Exception.Message
    Write-AppLog $text -Level "ERROR"
    Show-AppDialog -Message $text -Kind "Error"
    exit 1
}

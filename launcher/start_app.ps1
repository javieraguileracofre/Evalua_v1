#Requires -Version 5.1
<#
.SYNOPSIS
    Inicia EvaluaERP en localhost y abre el navegador.
.DESCRIPTION
    Pensado para el acceso directo del escritorio. No requiere PowerShell a la vista:
    run_hidden.vbs lo ejecuta en segundo plano.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

Set-Location -LiteralPath (Get-ProjectRoot)

$mutex = $null
$createdNew = $false
try {
    $mutex = New-Object System.Threading.Mutex($true, "Local\EvaluaERP-localhost-launcher", [ref]$createdNew)
} catch {
    $createdNew = $true
}

try {
    $port = Get-AppPort
    $url = Get-AppUrl
    Write-AppLog "=== Inicio EvaluaERP ==="
    Write-AppLog ("Carpeta: {0}" -f (Get-ProjectRoot))
    Write-AppLog "URL local: $url"

    $listenPid = Get-ListeningPid -Port $port
    $savedPid = Get-SavedPid

    if ($listenPid) {
        if (Test-IsOurAppProcess -ProcessId $listenPid) {
            Write-AppLog "La aplicacion ya estaba en marcha (PID $listenPid). Solo se abre el navegador."
            Open-AppBrowser
            exit 0
        }
        $cmd = Get-ProcessCommandLine -ProcessId $listenPid
        $msg = "El puerto $port ya esta ocupado por otro programa (PID $listenPid)."
        if ($cmd) { $msg += "`r`n`r`nProceso: $cmd" }
        $msg += "`r`n`r`nCierre ese programa o cambie UVICORN_PORT en el archivo .env."
        Write-AppLog $msg -Level "ERROR"
        Show-AppDialog -Message $msg -Kind "Error"
        exit 1
    }

    if ($savedPid) {
        Write-AppLog "Hay un proceso nuestro arrancando (PID $savedPid). Esperando a que el puerto $port quede listo..."
        $ready = Wait-AppReady -Port $port -TimeoutSeconds 90 -ProcessId $savedPid
        if ($ready) {
            Open-AppBrowser
            exit 0
        }
        Write-AppLog "El proceso anterior no llego a escuchar en el puerto. Se intenta un arranque nuevo." -Level "WARN"
        Stop-ProcessTree -ProcessId $savedPid
        Clear-PidFile
    }

    if (-not $createdNew) {
        Write-AppLog "Otro arranque ya esta en curso. Esperando..."
        $ready = Wait-AppReady -Port $port -TimeoutSeconds 90
        if ($ready) {
            Open-AppBrowser
            exit 0
        }
        Show-AppDialog -Message "No se pudo iniciar la aplicacion (otro intento de arranque no termino a tiempo). Revise logs\launcher-*.log" -Kind "Error"
        exit 1
    }

    $python = Ensure-VirtualEnv
    Write-AppLog "Python: $python"
    Ensure-Dependencies -PythonExe $python

    $mainPy = Join-Path (Get-ProjectRoot) "main.py"
    if (-not (Test-Path -LiteralPath $mainPy)) {
        throw "No se encontro main.py en la carpeta del proyecto."
    }

    $stdout = Get-UvicornLogFile
    $stderr = Join-Path (Get-LogsDir) "uvicorn.err.log"
    # Truncar logs de servidor en cada arranque para que el diagnostico sea del intento actual.
    Set-Content -LiteralPath $stdout -Value ("--- {0} ---" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding UTF8
    Set-Content -LiteralPath $stderr -Value "" -Encoding UTF8

    Write-AppLog "Lanzando main.py (host/puerto salen de .env: UVICORN_HOST / UVICORN_PORT)..."
    $proc = Start-Process -FilePath $python -ArgumentList @("-u", "main.py") -WorkingDirectory (Get-ProjectRoot) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    if (-not $proc) {
        throw "Start-Process no devolvio un proceso."
    }
    Save-AppPid -ProcessId $proc.Id
    Write-AppLog "Proceso iniciado: PID $($proc.Id)"

    $ready = Wait-AppReady -Port $port -TimeoutSeconds 90 -ProcessId $proc.Id
    if (-not $ready) {
        $tail = ""
        if (Test-Path -LiteralPath $stderr) {
            $tail = ((Get-Content -LiteralPath $stderr -ErrorAction SilentlyContinue) | Select-Object -Last 20) -join "`r`n"
        }
        if (-not $tail -and (Test-Path -LiteralPath $stdout)) {
            $tail = ((Get-Content -LiteralPath $stdout -ErrorAction SilentlyContinue) | Select-Object -Last 20) -join "`r`n"
        }
        $msg = "La aplicacion no arranco a tiempo en $url ."
        $msg += "`r`nRevise logs\uvicorn.err.log y que la base de datos este disponible."
        if ($tail) { $msg += "`r`n`r`n--- Ultimas lineas ---`r`n$tail" }
        Write-AppLog $msg -Level "ERROR"
        if (Test-ProcessAlive -ProcessId $proc.Id) {
            Stop-ProcessTree -ProcessId $proc.Id
        }
        Clear-PidFile
        Show-AppDialog -Message $msg -Kind "Error"
        exit 1
    }

    Write-AppLog "Servidor listo en $url"
    Open-AppBrowser
    exit 0
}
catch {
    $text = $_.Exception.Message
    Write-AppLog $text -Level "ERROR"
    Show-AppDialog -Message $text -Kind "Error"
    exit 1
}
finally {
    if ($mutex) {
        if ($createdNew) {
            try { $mutex.ReleaseMutex() | Out-Null } catch { }
        }
        try { $mutex.Dispose() } catch { }
    }
}

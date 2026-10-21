#Requires -Version 5.1
# Funciones compartidas del launcher local (Windows, sin admin).
# Compatible con PowerShell 5.1 (el que trae Windows).

Set-StrictMode -Version Latest

# Capturar al cargar este archivo (si se evaluara $PSScriptRoot dentro de una
# funcion, PowerShell devolveria el script llamador).
$script:LauncherDirResolved = $PSScriptRoot
if (-not $script:LauncherDirResolved) {
    $script:LauncherDirResolved = Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Get-LauncherDir {
    return $script:LauncherDirResolved
}

function Get-ProjectRoot {
    return (Split-Path -Parent (Get-LauncherDir))
}

function Get-LogsDir {
    $dir = Join-Path (Get-ProjectRoot) "logs"
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    return $dir
}

function Get-PidFile {
    return (Join-Path (Get-LogsDir) "app.pid")
}

function Get-UvicornLogFile {
    return (Join-Path (Get-LogsDir) "uvicorn.log")
}

function Get-LauncherLogFile {
    $stamp = Get-Date -Format "yyyyMMdd"
    return (Join-Path (Get-LogsDir) "launcher-$stamp.log")
}

function Write-AppLog {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR")][string]$Level = "INFO"
    )
    $line = "{0} | {1} | {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    try {
        Add-Content -LiteralPath (Get-LauncherLogFile) -Value $line -Encoding UTF8
    } catch {
        # No bloquear el arranque si el log no se puede escribir (OneDrive, etc.).
    }
    Write-Host $line
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Key,
        [string]$Default = $null
    )
    $path = Join-Path (Get-ProjectRoot) ".env"
    if (-not (Test-Path -LiteralPath $path)) {
        return $Default
    }
    foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#")) { continue }
        $eq = $t.IndexOf("=")
        if ($eq -lt 1) { continue }
        $k = $t.Substring(0, $eq).Trim()
        if ($k -ne $Key) { continue }
        $v = $t.Substring($eq + 1).Trim()
        if ($v.Length -ge 2) {
            $q = $v[0]
            if (($q -eq [char]34 -or $q -eq [char]39) -and $v[-1] -eq $q) {
                $v = $v.Substring(1, $v.Length - 2)
            }
        }
        return $v
    }
    return $Default
}

function Get-AppPort {
    $raw = Get-DotEnvValue -Key "UVICORN_PORT" -Default $null
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $raw = Get-DotEnvValue -Key "PORT" -Default "8000"
    }
    $port = 8000
    if (-not [int]::TryParse($raw, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
        return 8000
    }
    return $port
}

function Get-AppUrl {
    return ("http://127.0.0.1:{0}" -f (Get-AppPort))
}

function Show-AppDialog {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [string]$Title = "EvaluaERP",
        [ValidateSet("Info", "Error", "Warning")][string]$Kind = "Info"
    )
    try {
        Add-Type -AssemblyName System.Windows.Forms | Out-Null
        $icon = [System.Windows.Forms.MessageBoxIcon]::Information
        if ($Kind -eq "Error") { $icon = [System.Windows.Forms.MessageBoxIcon]::Error }
        elseif ($Kind -eq "Warning") { $icon = [System.Windows.Forms.MessageBoxIcon]::Warning }
        [System.Windows.Forms.MessageBox]::Show(
            $Message,
            $Title,
            [System.Windows.Forms.MessageBoxButtons]::OK,
            $icon
        ) | Out-Null
    } catch {
        Write-Host $Message
    }
}

function Get-VenvPython {
    $root = Get-ProjectRoot
    $candidates = @(
        (Join-Path $root "env\Scripts\python.exe"),
        (Join-Path $root ".venv\Scripts\python.exe"),
        (Join-Path $root "venv\Scripts\python.exe")
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Test-UsablePython {
    param([Parameter(Mandatory = $true)][string]$Exe)
    if (-not (Test-Path -LiteralPath $Exe)) { return $false }
    # El alias de Microsoft Store no es un Python real.
    if ($Exe -match "WindowsApps") { return $false }
    try {
        $out = & $Exe -c "import sys; print(sys.version_info[0])" 2>$null
        return ($LASTEXITCODE -eq 0 -and "$out".Trim() -ge "3")
    } catch {
        return $false
    }
}

function Get-SystemPython {
    $cmds = @("py", "python", "python3")
    foreach ($name in $cmds) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $exe = $cmd.Source
        if ($name -eq "py") {
            try {
                $probe = & $exe -3 -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($probe)) {
                    $exe = "$probe".Trim()
                }
            } catch {
                continue
            }
        }
        if (Test-UsablePython -Exe $exe) { return $exe }
    }
    return $null
}

function Ensure-VirtualEnv {
    $existing = Get-VenvPython
    if ($existing) { return $existing }

    $systemPy = Get-SystemPython
    if (-not $systemPy) {
        throw "No se encontro Python 3 en este equipo. Instale Python 3.11+ desde python.org (marque 'Add python.exe to PATH') y vuelva a intentar."
    }

    $venvDir = Join-Path (Get-ProjectRoot) "env"
    Write-AppLog "No habia entorno virtual. Creando: $venvDir"
    & $systemPy -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo crear el entorno virtual en $venvDir"
    }
    $py = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $py)) {
        throw "El entorno virtual se creo pero no aparece python.exe en $py"
    }
    return $py
}

function Test-PythonModule {
    param(
        [Parameter(Mandatory = $true)][string]$PythonExe,
        [Parameter(Mandatory = $true)][string]$ModuleName
    )
    & $PythonExe -c "import $ModuleName" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Dependencies {
    param([Parameter(Mandatory = $true)][string]$PythonExe)
    $req = Join-Path (Get-ProjectRoot) "requirements.txt"
    if (-not (Test-Path -LiteralPath $req)) {
        throw "No se encontro requirements.txt en la carpeta del proyecto."
    }
    $needInstall = -not (Test-PythonModule -PythonExe $PythonExe -ModuleName "fastapi")
    if (-not $needInstall) {
        $needInstall = -not (Test-PythonModule -PythonExe $PythonExe -ModuleName "uvicorn")
    }
    if (-not $needInstall) {
        Write-AppLog "Dependencias OK (fastapi/uvicorn ya estan instalados)."
        return
    }
    Write-AppLog "Instalando dependencias desde requirements.txt (solo esta vez o cuando falten)..."
    & $PythonExe -m pip install --disable-pip-version-check -r $req
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo pip install -r requirements.txt. Revise logs y la conexion a Internet."
    }
}

function Get-ListeningPid {
    param([Parameter(Mandatory = $true)][int]$Port)
    try {
        $conns = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)
        if ($conns.Count -gt 0) {
            return [int]$conns[0].OwningProcess
        }
    } catch {
        # Fallback para ediciones sin Get-NetTCPConnection.
    }
    try {
        $escaped = [regex]::Escape(":$Port")
        $lines = netstat -ano | Select-String -Pattern "$escaped\s+.*LISTENING"
        foreach ($m in $lines) {
            if ($m.Line -match "\s(\d+)\s*$") {
                return [int]$Matches[1]
            }
        }
    } catch { }
    return $null
}

function Test-ProcessAlive {
    param([int]$ProcessId)
    if (-not $ProcessId -or $ProcessId -le 0) { return $false }
    $p = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    return [bool]$p
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)
    if (-not $ProcessId) { return "" }
    try {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($p) { return [string]$p.CommandLine }
    } catch { }
    return ""
}

function Test-IsOurAppProcess {
    param([int]$ProcessId)
    if (-not (Test-ProcessAlive -ProcessId $ProcessId)) { return $false }
    $cmd = Get-ProcessCommandLine -ProcessId $ProcessId
    $root = (Get-ProjectRoot)
    $rootNorm = $root.Replace("\", "/").ToLowerInvariant()
    $cmdNorm = $cmd.Replace("\", "/").ToLowerInvariant()
    if ($cmdNorm -like "*main.py*") { return $true }
    if ($cmdNorm -like "*main:app*") { return $true }
    if ($rootNorm -and $cmdNorm -like "*$rootNorm*") { return $true }
    $saved = Get-SavedPid
    if ($saved -and $saved -eq $ProcessId) { return $true }
    return $false
}

function Get-SavedPid {
    $file = Get-PidFile
    if (-not (Test-Path -LiteralPath $file)) { return $null }
    try {
        $raw = (Get-Content -LiteralPath $file -TotalCount 1).Trim()
        $id = 0
        if ([int]::TryParse($raw, [ref]$id) -and (Test-ProcessAlive -ProcessId $id)) {
            return $id
        }
    } catch { }
    return $null
}

function Save-AppPid {
    param([int]$ProcessId)
    Set-Content -LiteralPath (Get-PidFile) -Value "$ProcessId" -Encoding ASCII
}

function Clear-PidFile {
    $file = Get-PidFile
    if (Test-Path -LiteralPath $file) {
        Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
    }
}

function Wait-AppReady {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 90,
        [int]$ProcessId = 0
    )
    $url = "http://127.0.0.1:$Port/"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($ProcessId -gt 0 -and -not (Test-ProcessAlive -ProcessId $ProcessId)) {
            return $false
        }
        $listenPid = Get-ListeningPid -Port $Port
        if ($listenPid) {
            try {
                Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -MaximumRedirection 0 -ErrorAction Stop | Out-Null
                return $true
            } catch {
                # Cualquier respuesta HTTP (302 login, 500, etc.) significa que el servidor ya atiende.
                $resp = $_.Exception.Response
                if ($resp) { return $true }
            }
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Open-AppBrowser {
    $url = Get-AppUrl
    Write-AppLog "Abriendo navegador: $url"
    Start-Process $url
}

function Stop-ProcessTree {
    param([int]$ProcessId)
    if (-not $ProcessId) { return }
    # /T mata el arbol (necesario si uvicorn corre con reload).
    & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
}

function Get-PreferredIconPath {
    $custom = Join-Path (Get-LauncherDir) "app.ico"
    if (Test-Path -LiteralPath $custom) { return $custom }
    $py = Get-VenvPython
    if ($py -and (Test-Path -LiteralPath $py)) { return $py }
    $sys = "$env:SystemRoot\System32\wscript.exe"
    return $sys
}

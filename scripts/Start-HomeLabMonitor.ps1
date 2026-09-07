$ErrorActionPreference = 'Stop'

# Keep this script in the repo. Copy scripts\startHomeLabMonitor.bat to C:\scripts.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$AppPath = Join-Path $ProjectRoot 'run.py'
$Port = 8000
$LogDir = Join-Path $ProjectRoot 'logs'
$LogFile = Join-Path $LogDir 'monitor.log'

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Missing venv Python: $PythonExe. Create .venv and install requirements.txt first."
}
if (-not (Test-Path -LiteralPath $AppPath)) {
    throw "Missing app entry point: $AppPath"
}

function Get-PortListeners {
    param([int]$LocalPort)
    try {
        @(Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction Stop)
    }
    catch {
        @()
    }
}

function Get-ListenerIdentity {
    param([int]$ProcessId)
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $commandLine = $null
    try {
        $commandLine = (
            Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        ).CommandLine
    }
    catch {
        $commandLine = $null
    }
    [pscustomobject]@{
        ProcessId   = $ProcessId
        Name        = if ($proc) { $proc.Name } else { $null }
        Path        = if ($proc) { $proc.Path } else { $null }
        CommandLine = $commandLine
    }
}

function Test-IsThisMonitor {
    param(
        $Identity,
        [string]$PythonExe,
        [string]$AppPath
    )
    if (-not $Identity) {
        return $false
    }
    if ($Identity.Path -and [string]::Equals($Identity.Path, $PythonExe, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $commandLine = $Identity.CommandLine
    if (-not $commandLine) {
        return $false
    }
    if ($commandLine.IndexOf($AppPath, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
    }
    $hasVenvPython = $commandLine.IndexOf($PythonExe, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $hasRunPy = $commandLine.IndexOf('run.py', [StringComparison]::OrdinalIgnoreCase) -ge 0
    return ($hasVenvPython -and $hasRunPy)
}

function Get-LanIpv4Addresses {
    try {
        @(
            Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
                Where-Object {
                    $_.IPAddress -ne '127.0.0.1' -and
                    $_.AddressState -eq 'Preferred' -and
                    $_.PrefixOrigin -ne 'WellKnown' -and
                    $_.IPAddress -notlike '169.254.*'
                } |
                Select-Object -ExpandProperty IPAddress
        ) | Sort-Object -Unique
    }
    catch {
        @()
    }
}

function Write-DashboardUrls {
    Write-Output "Dashboard: http://127.0.0.1:$Port"
    $lanIps = @(Get-LanIpv4Addresses)
    if ($lanIps.Count -eq 0) {
        Write-Output "Also try this machine's LAN IP on port $Port."
        return
    }
    foreach ($ip in $lanIps) {
        Write-Output ("LAN:       http://{0}:{1}" -f $ip, $Port)
    }
}

$listeners = @(Get-PortListeners -LocalPort $Port)
if ($listeners.Count -gt 0) {
    $pids = @($listeners.OwningProcess | Sort-Object -Unique)
    $ours = @()
    $others = @()
    foreach ($listenerPid in $pids) {
        $identity = Get-ListenerIdentity -ProcessId $listenerPid
        if (Test-IsThisMonitor -Identity $identity -PythonExe $PythonExe -AppPath $AppPath) {
            $ours += $identity
        }
        else {
            $others += $identity
        }
    }

    if ($ours.Count -gt 0) {
        $shown = $ours | ForEach-Object { "PID $($_.ProcessId)" }
        Write-Output ("Home Lab Monitor is already running ({0})." -f ($shown -join ', '))
        Write-DashboardUrls
        exit 0
    }

    $conflict = $others | ForEach-Object {
        $label = if ($_.Name) { $_.Name } else { 'unknown process' }
        "PID $($_.ProcessId) ($label)"
    }
    Write-Warning ("TCP {0} is in use by {1}. Not starting Home Lab Monitor." -f $Port, ($conflict -join ', '))
    exit 1
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -LiteralPath $LogFile -Value "`r`n==== $stamp starting Home Lab Monitor ====" -Encoding utf8

$startCommand = @"
Set-Location -LiteralPath '$ProjectRoot'
& '$PythonExe' 'run.py' *>> '$LogFile'
"@

Start-Process -FilePath 'powershell.exe' -ArgumentList @(
    '-NoProfile',
    '-WindowStyle', 'Hidden',
    '-ExecutionPolicy', 'Bypass',
    '-Command', $startCommand
) -WorkingDirectory $ProjectRoot -WindowStyle Hidden | Out-Null

$deadline = (Get-Date).AddSeconds(8)
$started = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 400
    if ((Get-PortListeners -LocalPort $Port).Count -gt 0) {
        $started = $true
        break
    }
}

if (-not $started) {
    Write-Warning "Started Home Lab Monitor but TCP $Port is not listening yet. Check $LogFile"
    exit 1
}

$listenerPids = @(
    (Get-PortListeners -LocalPort $Port).OwningProcess | Sort-Object -Unique
)
Write-Output ("Home Lab Monitor started ({0})." -f (($listenerPids | ForEach-Object { "PID $_" }) -join ', '))
Write-DashboardUrls
exit 0

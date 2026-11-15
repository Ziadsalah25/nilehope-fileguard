# ScanNetwork.ps1
# Simple network discovery script for the Nile of Hope DLP proof‑of‑concept.
# It scans the local IPv4 subnet, pings each address, and records any host that replies.
# The results are written to 'network_devices.json' in the same folder.

param(
    [int]$TimeoutSec = 1,   # Ping timeout per host
    [int]$Parallel = 32    # Number of concurrent pings (PowerShell jobs)
)

function Get-SubnetInfo {
    # Retrieve the first non‑loopback IPv4 address and its mask
    $addr = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "*" |
            Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.PrefixLength -gt 0 } |
            Select-Object -First 1
    if (-not $addr) { throw "No IPv4 address found on this machine." }
    return $addr
}

$info = Get-SubnetInfo
$base = ($info.IPAddress -as [System.Net.IPAddress]).GetAddressBytes()
$prefix = $info.PrefixLength

# Compute network start address (zero out host bits)
$mask = [uint32](([math]::pow(2, $prefix) - 1) -shl (32 - $prefix))
$baseInt = [BitConverter]::ToUInt32([byte[]]::Reverse($base),0)
$networkInt = $baseInt -band $mask

# Helper to turn integer back into dotted string
function IntToIp([uint32]$int) {
    $bytes = [BitConverter]::GetBytes($int)
    [array]::Reverse($bytes)
    return ($bytes -join '.')
}

$hosts = @()
$jobs = @()
for ($i = 1; $i -lt 255; $i++) {
    $ipInt = $networkInt + $i
    $ip = IntToIp $ipInt
    $jobs += Start-Job -ScriptBlock {
        param($ip, $t)
        if (Test-Connection -ComputerName $ip -Count 1 -Quiet -TimeoutSeconds $t) {
            $name = try { (Resolve-DnsName $ip -ErrorAction Stop).NameHost } catch { $null }
            return @{ ip=$ip; hostname=$name }
        }
        return $null
    } -ArgumentList $ip, $TimeoutSec
    # Throttle parallel jobs
    if ($jobs.Count -ge $Parallel) {
        $j = Wait-Job -Any $jobs
        $result = Receive-Job $j
        if ($result) { $hosts += $result }
        Remove-Job $j
        $jobs = $jobs | Where-Object { $_.State -eq 'Running' }
    }
}
# Wait for remaining jobs
foreach ($j in $jobs) {
    Wait-Job $j
    $result = Receive-Job $j
    if ($result) { $hosts += $result }
    Remove-Job $j
}

# Save to JSON
$outFile = Join-Path $PSScriptRoot 'network_devices.json'
$hosts | ConvertTo-Json -Depth 3 | Set-Content -Path $outFile -Encoding UTF8
Write-Host "Scan completed. $(($hosts).Count) devices saved to $outFile" -ForegroundColor Green

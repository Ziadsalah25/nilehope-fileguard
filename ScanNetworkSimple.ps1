# ScanNetworkSimple.ps1
# Writes a JSON file (network_devices.json) with any host that replies.

param(
    [Parameter(Mandatory=$true)][string[]]$Subnets,
    [int]$TimeoutSec = 1,
    [int]$Parallel = 64   # number of concurrent jobs
)


function Ping-Subnet {
    param($subnet,$timeout,$parallel)
    $net, $mask = $subnet -split '/'
    $baseBytes = $net.Split('.') | ForEach-Object {[int]$_}
    $start = ($baseBytes[0] -shl 24) -bor ($baseBytes[1] -shl 16) -bor ($baseBytes[2] -shl 8) -bor 1
    $end   = ($baseBytes[0] -shl 24) -bor ($baseBytes[1] -shl 16) -bor ($baseBytes[2] -shl 8) -bor 254
    $jobs = @()
    $hosts = @()
    for ($i = $start; $i -le $end; $i++) {
        $ip = [System.Net.IPAddress]::Parse(($i -shr 24) -band 0xFF).ToString() + '.' +
              [System.Net.IPAddress]::Parse(($i -shr 16) -band 0xFF).ToString() + '.' +
              [System.Net.IPAddress]::Parse(($i -shr 8) -band 0xFF).ToString() + '.' +
              [System.Net.IPAddress]::Parse($i -band 0xFF).ToString()
        $jobs += Start-Job -ScriptBlock {
            param($addr,$t)
            if (Test-Connection -ComputerName $addr -Count 1 -Quiet -TimeoutSeconds $t) {
                $name = try { (Resolve-DnsName $addr -ErrorAction Stop).NameHost } catch { $null }
                return @{ ip=$addr; hostname=$name }
            }
            return $null
        } -ArgumentList $ip,$timeout
        if ($jobs.Count -ge $parallel) {
            $j = Wait-Job -Any $jobs
            $res = Receive-Job $j
            if ($res) { $hosts += $res }
            Remove-Job $j
            $jobs = $jobs | Where-Object { $_.State -eq 'Running' }
        }
    }
    foreach ($j in $jobs) {
        Wait-Job $j
        $res = Receive-Job $j
        if ($res) { $hosts += $res }
        Remove-Job $j
    }
    return $hosts
}

$allHosts = @()
foreach ($sn in $subnets) {
    $allHosts += Ping-Subnet -subnet $sn -timeout $TimeoutSec -parallel $Parallel
}

$outFile = Join-Path $PSScriptRoot 'network_devices.json'
$allHosts | ConvertTo-Json -Depth 3 | Set-Content -Path $outFile -Encoding UTF8
Write-Host "Found $($allHosts.Count) devices – saved to $outFile" -ForegroundColor Green

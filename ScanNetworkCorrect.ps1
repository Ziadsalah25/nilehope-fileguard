# ScanNetworkCorrect.ps1
# For each IP we ping (Test-Connection) and, if it replies, we try a reverse DNS lookup.
# Results are saved as JSON to network_devices.json in the script directory.

param(
    [Parameter(Mandatory=$true)][string[]]$Subnets,
    [int]$TimeoutMs = 1000,   # milliseconds for the native ping command
    [int]$Parallel = 64      # max concurrent ping jobs
)


function Ping-Subnet {
    param($subnet,$timeout,$parallel)
    $base, $mask = $subnet -split '/'
    $octets = $base.Split('.')
    $networkPrefix = "$($octets[0]).$($octets[1]).$($octets[2])."
    $jobs = @()
    $hosts = @()
    for ($i = 1; $i -le 254; $i++) {
        $ip = "$networkPrefix$i"
        $jobs += Start-Job -ScriptBlock {
            param($addr,$t)
            # Use the legacy ping.exe to honour timeout in ms
            $result = & ping -n 1 -w $t $addr | Out-String
            if ($result -match 'Reply from') {
                try {
                    $name = (Resolve-DnsName $addr -ErrorAction Stop).NameHost
                } catch { $name = $null }
                return @{ ip=$addr; hostname=$name }
            }
            return $null
        } -ArgumentList $ip,$timeout
        # Throttle
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

$all = @()
foreach ($sn in $subnets) {
    $all += Ping-Subnet -subnet $sn -timeout $TimeoutMs -parallel $Parallel
}

$outFile = Join-Path $PSScriptRoot 'network_devices.json'
$all | ConvertTo-Json -Depth 3 | Set-Content -Path $outFile -Encoding UTF8
Write-Host "Discovered $($all.Count) devices – results saved to $outFile" -ForegroundColor Green

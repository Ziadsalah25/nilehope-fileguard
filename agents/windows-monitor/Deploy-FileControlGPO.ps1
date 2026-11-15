# Compatibility entry point. Prepare a deployment bundle; follow the printed GPMC registration steps.
param([Parameter(Mandatory=$true)][string]$ServerUrl,
      [Parameter(Mandatory=$true)][string]$EnrollToken,
      [string[]]$FileServers=@(),
      [ValidateSet('pilot','ring20','ring50','all')][string]$Ring='pilot',
      [string]$OutputDir=(Join-Path $PWD 'gpo-deployment'))
& (Join-Path $PSScriptRoot 'Prepare-GPODeployment.ps1') @PSBoundParameters

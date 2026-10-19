# Read-only USB report for a PC without Python or a working Glideleaf install.
param([switch]$Copy, [string]$OutputPath = "")

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

$devices = @(Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
    Where-Object { $_.Present -and $_.PNPDeviceID -like 'USB\VID_*' } |
    ForEach-Object {
        [PSCustomObject]@{
            hardware_id = ($_.PNPDeviceID -split '\\')[1]
            name = $_.Name
            class = $_.PNPClass
            service = $_.Service
            status = $_.Status
            problem_code = $_.ConfigManagerErrorCode
            compatible_ids = @($_.CompatibleID)
        }
    })

$report = [PSCustomObject]@{
    app = 'Glideleaf standalone USB diagnostics'
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    usb_node_count = $devices.Count
    usb_devices = $devices
    scope = 'Read-only USB enumeration. No driver changes. Device serial suffixes omitted.'
}
$json = ConvertTo-Json -InputObject $report -Depth 5
if ($OutputPath) {
    $absoluteOutputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
    [System.IO.File]::WriteAllText($absoluteOutputPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}
if ($Copy) { Set-Clipboard -Value $json }
Write-Output $json

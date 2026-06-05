$ErrorActionPreference = 'Stop'
$path = Join-Path $env:TEMP 'pq_reference.xlsx'
if (Test-Path $path) { Remove-Item $path -Force }
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false
$xl.DisplayAlerts = $false
$wb = $xl.Workbooks.Add()
$formula = "let`r`n    Source = 1`r`nin`r`n    Source"
[void]$wb.Queries.Add('Databank_Reference', $formula)
$wb.SaveCopyAs($path)
$wb.Close($false)
$xl.Quit()
if (-not (Test-Path $path)) { throw "File not created at $path" }
Copy-Item $path (Join-Path (Split-Path $PSScriptRoot -Parent) 'pq_reference.xlsx') -Force
Write-Host "saved" (Join-Path (Split-Path $PSScriptRoot -Parent) 'pq_reference.xlsx')

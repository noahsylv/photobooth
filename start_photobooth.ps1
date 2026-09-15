Set-Location -Path $PSScriptRoot
& .\.venv\Scripts\Activate.ps1
mpremote connect COM3 fs cp pico_main.py :main.py
mpremote connect COM3 reset
python app.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Photobooth exited with an error. Press any key to close..."
    [void][System.Console]::ReadKey($true)
}

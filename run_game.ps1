# LSL modunda oyunu başlatır: önce BCI_Control kaynağı, sonra oyun.
# Kullanım (proje klasöründe, kendi PowerShell penceresinde):  .\run_game.ps1
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
Set-Location $PSScriptRoot

$src = Start-Process -FilePath $py -ArgumentList "-m", "src.control.keyboard_source" -PassThru
Start-Sleep -Seconds 3
try {
    & $py -m src.game.ball_roll
} finally {
    if ($src -and -not $src.HasExited) { Stop-Process -Id $src.Id -Force }
}

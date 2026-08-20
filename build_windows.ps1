$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "[1/6] Preparando ambiente virtual"
if (-not (Test-Path ".build-venv")) {
    py -3.12 -m venv .build-venv
}
& ".\.build-venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.build-venv\Scripts\python.exe" -m pip install -r requirements-build.txt

Write-Host "[2/6] Gerando ícone"
& ".\.build-venv\Scripts\python.exe" scripts\generate_icon.py

Write-Host "[3/6] Executando testes"
& ".\.build-venv\Scripts\python.exe" -m unittest discover -s tests -v

Write-Host "[4/6] Gerando PrimeAITrader.exe"
& ".\.build-venv\Scripts\pyinstaller.exe" --noconfirm --clean PrimeAITrader.spec
New-Item -ItemType Directory -Force release | Out-Null
Copy-Item "dist\PrimeAITrader.exe" "release\PrimeAITrader.exe" -Force

Write-Host "[5/6] Localizando Inno Setup"
$InnoCandidates = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$Iscc = $InnoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) {
    throw "Inno Setup 6 não encontrado. Instale em https://jrsoftware.org/isinfo.php e execute novamente."
}

Write-Host "[6/6] Gerando PrimeAITrader-Setup-x64.exe"
& $Iscc "installer\PrimeAITrader.iss"

Write-Host "Build concluído em $ProjectRoot\release"


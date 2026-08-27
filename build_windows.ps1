$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step falhou com código $LASTEXITCODE. O instalador não será publicado."
    }
}

Write-Host "[1/6] Preparando ambiente virtual"
if (-not (Test-Path ".build-venv")) {
    py -3.12 -m venv .build-venv
    Assert-NativeSuccess "Criação do ambiente Python"
}
& ".\.build-venv\Scripts\python.exe" -m pip install --upgrade pip
Assert-NativeSuccess "Atualização do pip"
& ".\.build-venv\Scripts\python.exe" -m pip install -r requirements-build.txt
Assert-NativeSuccess "Instalação das dependências"

Write-Host "[2/6] Gerando ícone"
& ".\.build-venv\Scripts\python.exe" scripts\generate_icon.py
Assert-NativeSuccess "Geração do ícone"

Write-Host "[3/6] Executando testes"
& ".\.build-venv\Scripts\python.exe" -m unittest discover -s tests -v
Assert-NativeSuccess "Suíte completa de testes"
& ".\.build-venv\Scripts\python.exe" -m compileall -q prime_ai_trader tests
Assert-NativeSuccess "Compilação estática do código"
& ".\.build-venv\Scripts\python.exe" -c "from tkinter import filedialog, messagebox, ttk; print('Tkinter completo')"
Assert-NativeSuccess "Validação do Tkinter completo"

Write-Host "[4/6] Gerando executável"
& ".\.build-venv\Scripts\pyinstaller.exe" --noconfirm --clean PrimeAITrader.spec
Assert-NativeSuccess "Empacotamento do aplicativo"
New-Item -ItemType Directory -Force release | Out-Null
Copy-Item "dist\PrimeAITrader.exe" "release\PrimeAITrader.exe" -Force

Write-Host "[5/6] Localizando Inno Setup"
$InnoCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:ChocolateyInstall\bin\ISCC.exe"
)
$Iscc = $InnoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) {
    throw "Inno Setup 6 não encontrado. Instale em https://jrsoftware.org/isinfo.php e execute novamente."
}

Write-Host "[6/6] Gerando PrimeTrader-Setup-x64.exe"
& $Iscc "installer\PrimeAITrader.iss"
Assert-NativeSuccess "Compilação do instalador"

Write-Host "Build concluído em $ProjectRoot\release"

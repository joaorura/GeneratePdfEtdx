# Script para criar atalho do Windows para o Gerador de PDF
# Execute este script como administrador se necessário

$WshShell = New-Object -comObject WScript.Shell

# Caminho atual do script
$CurrentPath = Get-Location
$GuiPath = Join-Path $CurrentPath "gui.py"
$BatchPath = Join-Path $CurrentPath "executar_gui.bat"

# Caminho para o Python (tenta encontrar automaticamente)
$PythonPath = ""
$PossiblePaths = @(
    "python",
    "python3",
    "C:\Python*\python.exe",
    "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python*\python.exe",
    "C:\Program Files\Python*\python.exe",
    "C:\Program Files (x86)\Python*\python.exe"
)

foreach ($path in $PossiblePaths) {
    try {
        if ($path -like "*python*") {
            $found = Get-Command $path -ErrorAction SilentlyContinue
            if ($found) {
                $PythonPath = $found.Source
                break
            }
        } else {
            $result = & $path --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonPath = $path
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $PythonPath) {
    Write-Host "ERRO: Python não encontrado no sistema!" -ForegroundColor Red
    Write-Host "Por favor, instale o Python 3.7+ e tente novamente." -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 1
}

Write-Host "Python encontrado em: $PythonPath" -ForegroundColor Green

# Verifica se o arquivo gui.py existe
if (-not (Test-Path $GuiPath)) {
    Write-Host "ERRO: Arquivo gui.py não encontrado!" -ForegroundColor Red
    Write-Host "Certifique-se de que este script está na mesma pasta do gui.py" -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Cria o atalho na área de trabalho
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "Gerador de PDF.lnk"

try {
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $PythonPath
    $Shortcut.Arguments = "`"$GuiPath`""
    $Shortcut.WorkingDirectory = $CurrentPath
    $Shortcut.Description = "Gerador de PDF a partir de arquivos .etdx"
    $Shortcut.IconLocation = Join-Path $CurrentPath "icons\pdf_gear.ico"
    $Shortcut.Save()
    
    Write-Host "Atalho criado com sucesso na área de trabalho!" -ForegroundColor Green
    Write-Host "Caminho: $ShortcutPath" -ForegroundColor Cyan
    
} catch {
    Write-Host "ERRO ao criar atalho: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Pergunta se quer criar atalho no menu iniciar também
$CreateStartMenu = Read-Host "Deseja criar atalho no Menu Iniciar também? (s/n)"
if ($CreateStartMenu -eq "s" -or $CreateStartMenu -eq "S") {
    try {
        $StartMenuPath = [Environment]::GetFolderPath("StartMenu")
        $StartMenuShortcutPath = Join-Path $StartMenuPath "Gerador de PDF.lnk"
        
        $StartMenuShortcut = $WshShell.CreateShortcut($StartMenuShortcutPath)
        $StartMenuShortcut.TargetPath = $PythonPath
        $StartMenuShortcut.Arguments = "`"$GuiPath`""
        $StartMenuShortcut.WorkingDirectory = $CurrentPath
        $StartMenuShortcut.Description = "Gerador de PDF a partir de arquivos .etdx"
        $StartMenuShortcut.IconLocation = Join-Path $CurrentPath "icons\pdf_gear.ico"
        $StartMenuShortcut.Save()
        
        Write-Host "Atalho criado no Menu Iniciar!" -ForegroundColor Green
        Write-Host "Caminho: $StartMenuShortcutPath" -ForegroundColor Cyan
        
    } catch {
        Write-Host "ERRO ao criar atalho no Menu Iniciar: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`nProcesso concluído!" -ForegroundColor Green
Write-Host "Você pode agora usar o atalho 'Gerador de PDF' para executar o programa." -ForegroundColor Yellow
Read-Host "Pressione Enter para sair" 
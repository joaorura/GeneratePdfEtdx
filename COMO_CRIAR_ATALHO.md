# Como Criar Atalho do Windows para o Gerador de PDF

Este documento explica como criar atalhos do Windows para executar facilmente o `gui.py` (interface gráfica do Gerador de PDF).

## Opções Disponíveis

### 1. Arquivo Batch (.bat) - Mais Simples
O arquivo `executar_gui.bat` já foi criado e pode ser usado diretamente:
- **Duplo clique** no arquivo `executar_gui.bat`
- Ou execute via linha de comando: `executar_gui.bat`

### 2. Script PowerShell - Cria Atalho Automático
O arquivo `criar_atalho.ps1` cria automaticamente um atalho na área de trabalho:

#### Como usar:
1. **Clique com botão direito** no arquivo `criar_atalho.ps1`
2. Selecione **"Executar com PowerShell"**
3. Se aparecer aviso de segurança, clique em **"Executar mesmo assim"**
4. O script irá:
   - Detectar automaticamente o Python instalado
   - Criar um atalho na área de trabalho
   - Perguntar se quer criar atalho no Menu Iniciar também

### 3. Criação Manual do Atalho

#### Método 1: Via Explorador de Arquivos
1. Navegue até a pasta onde está o `gui.py`
2. **Clique com botão direito** no arquivo `gui.py`
3. Selecione **"Criar atalho"**
4. O atalho será criado na mesma pasta
5. **Arraste** o atalho para a área de trabalho ou Menu Iniciar

#### Método 2: Via Propriedades do Atalho
1. **Clique com botão direito** na área de trabalho
2. Selecione **Novo** → **Atalho**
3. Em **"Digite o local do item"**, cole:
   ```
   python "C:\caminho\completo\para\gui.py"
   ```
4. Clique em **Próximo**
5. Digite o nome: **"Gerador de PDF"**
6. Clique em **Concluir**

#### Método 3: Via PowerShell (Comando Único)
Abra o PowerShell e execute:
```powershell
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Gerador de PDF.lnk")
$Shortcut.TargetPath = "python"
$Shortcut.Arguments = "`"$PWD\gui.py`""
$Shortcut.WorkingDirectory = $PWD
$Shortcut.IconLocation = "$PWD\icons\pdf_gear.ico"
$Shortcut.Save()
```

## Configurações do Atalho

### Ícone Personalizado
O atalho criado pelo script PowerShell usa automaticamente o ícone `icons\pdf_gear.ico`.

Para alterar o ícone manualmente:
1. **Clique com botão direito** no atalho
2. Selecione **Propriedades**
3. Clique em **Alterar ícone**
4. Navegue até `icons\pdf_gear.ico`

### Executar como Administrador (se necessário)
1. **Clique com botão direito** no atalho
2. Selecione **Propriedades**
3. Marque **"Executar como administrador"**
4. Clique em **OK**

## Solução de Problemas

### Erro: "Python não encontrado"
- Instale o Python 3.7 ou superior
- Certifique-se de que o Python está no PATH do sistema
- Ou especifique o caminho completo do Python no atalho

### Erro: "Arquivo gui.py não encontrado"
- Certifique-se de que o `gui.py` está na mesma pasta do atalho
- Ou ajuste o caminho no atalho para apontar para o local correto

### Erro: "Módulos não encontrados"
- Execute `pip install -r requirements.txt` para instalar as dependências
- Ou use o arquivo `install-ai.bat` se disponível

### Atalho não funciona
- Verifique se o caminho do Python está correto
- Teste executando `python gui.py` diretamente no terminal
- Verifique se todas as dependências estão instaladas

## Estrutura de Arquivos

```
teste/
├── gui.py                    # Interface gráfica principal
├── executar_gui.bat          # Script batch para execução
├── criar_atalho.ps1          # Script para criar atalho automático
├── icons/
│   └── pdf_gear.ico          # Ícone do programa
└── COMO_CRIAR_ATALHO.md      # Este arquivo
```

## Comandos Úteis

### Executar via linha de comando:
```bash
# Executar interface gráfica
python gui.py

# Executar via batch
executar_gui.bat

# Executar script de criação de atalho
powershell -ExecutionPolicy Bypass -File criar_atalho.ps1
```

### Verificar se Python está instalado:
```bash
python --version
```

### Instalar dependências:
```bash
pip install -r requirements.txt
``` 
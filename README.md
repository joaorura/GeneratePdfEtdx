# Gerador de PDF (.etdx)

Aplicação para gerar PDFs a partir de arquivos .etdx (arquivos ZIP disfarçados) com suporte a upscale inteligente de imagens.

## Funcionalidades

- ✅ Geração de PDF a partir de arquivos .etdx
- ✅ Suporte a múltiplos tamanhos de papel (A4, A3, A5, etc.)
- ✅ Upscale inteligente de imagens usando RealESRGAN
- ✅ Interface gráfica amigável
- ✅ Processamento paralelo de imagens (quando disponível)
- ✅ Configurações de qualidade (DPI, formato de imagem, qualidade JPEG)

## Instalação

1. Clone o repositório:
```bash
git clone <url-do-repositorio>
cd teste
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

## Uso

### Interface Gráfica
```bash
python gui.py
```

### Linha de Comando
```bash
# Gerar PDF a partir de arquivo .etdx
python cli.py arquivo.etdx --output saida.pdf

# Com configurações personalizadas
python cli.py arquivo.etdx --output saida.pdf --dpi 600 --img-format png --jpeg-quality 95

# Desabilitar upscale inteligente
python cli.py arquivo.etdx --no-upscale
```

## Compilação

Para criar um executável standalone:

```bash
# Windows
build.bat

# Linux/Mac
pyinstaller --onefile --windowed --name "GeradorPDF" gui.py
```

## Solução de Problemas

### Erro de Multiprocessing

Se você encontrar erros relacionados ao multiprocessing ao executar o aplicativo compilado:

```
AttributeError: Can't get attribute '_preprocess_image_worker' on <module 'pdf_generator.core'>
```

**Solução:** O aplicativo foi configurado para desabilitar automaticamente o multiprocessing em executáveis compilados. Isso pode tornar o processamento um pouco mais lento, mas evita os erros de compatibilidade.

### Para Habilitar Multiprocessing em Executáveis

Se você quiser tentar habilitar o multiprocessing em executáveis compilados:

1. Edite o arquivo `pdf_generator/core.py`
2. Mude a linha:
   ```python
   MULTIPROCESSING_AVAILABLE = not getattr(sys, 'frozen', False)
   ```
   Para:
   ```python
   MULTIPROCESSING_AVAILABLE = True
   ```

3. Recompile o aplicativo

**Nota:** Isso pode causar erros em alguns sistemas. Se ocorrerem problemas, volte para a configuração padrão.

### Problemas com RealESRGAN

Se o upscale inteligente não funcionar:

1. Verifique se o arquivo `weights/RealESRGAN_x4.pth` existe
2. O aplicativo automaticamente usa upscale simples como fallback
3. Para instalar RealESRGAN manualmente:
   ```bash
   pip install py-real-esrgan
   ```

## Estrutura do Projeto

```
teste/
├── pdf_generator/
│   ├── __init__.py
│   └── core.py          # Lógica principal de geração de PDF
├── icons/               # Ícones da aplicação
├── weights/             # Pesos do modelo RealESRGAN
├── gui.py              # Interface gráfica
├── cli.py              # Interface de linha de comando
├── main.py             # Versão simplificada (legado)
├── build.bat           # Script de compilação para Windows
├── runtime_hook.py     # Hook para PyInstaller
└── requirements.txt    # Dependências
```

## Configurações

### DPI (Dots Per Inch)
- **300 DPI**: Padrão, boa qualidade
- **600 DPI**: Alta qualidade, arquivos maiores

### Formato de Imagem
- **JPEG**: Menor tamanho, boa qualidade
- **PNG**: Maior tamanho, qualidade máxima

### Qualidade JPEG
- **80-100**: Quanto maior, melhor a qualidade e maior o arquivo

### Upscale Inteligente
- **Ativado**: Usa RealESRGAN para melhorar imagens pequenas
- **Desativado**: Usa redimensionamento simples

## Dependências

- `reportlab`: Geração de PDF
- `Pillow`: Processamento de imagens
- `py-real-esrgan`: Upscale inteligente (opcional)
- `tkinter`: Interface gráfica (incluído no Python)

## Licença

Este projeto está sob a licença MIT. 
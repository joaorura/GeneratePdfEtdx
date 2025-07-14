# Gerador de ETDX (.pdf → .etdx)

Este módulo permite converter arquivos PDF em arquivos .etdx editáveis, mantendo a qualidade e estrutura das páginas.

## Funcionalidades

- **Conversão PDF → ETDX**: Converte PDFs em arquivos .etdx editáveis
- **Detecção automática de tamanho**: Identifica automaticamente o tamanho do papel (A4, A3, A5, etc.)
- **Upscale simples**: Melhora a qualidade de imagens pequenas usando redimensionamento LANCZOS
- **Múltiplos formatos**: Suporte para JPEG e PNG
- **Configuração de DPI**: Opções de 300 DPI (padrão) ou 600 DPI (alta qualidade)
- **Processamento otimizado**: Sistema otimizado para melhor performance
- **Multiprocessing**: Processamento paralelo para melhor performance

## Instalação

### Dependências básicas
```bash
pip install -r requirements.txt
```



## Uso

### Interface Gráfica (GUI)
```bash
python etdx_gui.py
```
ou
```bash
executar_etdx_gui.bat
```

### Linha de Comando (CLI)
```bash
# Uso básico
python etdx_cli.py documento.pdf

# Com opções personalizadas
python etdx_cli.py documento.pdf --output meu_etdx.etdx --dpi 600 --format png --upscale

# Ajuda
python etdx_cli.py --help
```

## Opções de Configuração

### DPI (Qualidade)
- **300 DPI**: Padrão, boa qualidade, arquivo menor
- **600 DPI**: Alta qualidade, arquivo maior

### Formato de Imagem
- **JPEG**: Compressão com perda, arquivo menor
- **PNG**: Sem perda, arquivo maior

### Qualidade JPEG
- **80-100**: Controla a compressão JPEG
- **90**: Padrão recomendado

### Upscale Inteligente
- **Habilitado**: Usa RealESRGAN para melhorar imagens pequenas
- **Desabilitado**: Usa redimensionamento simples
- **Nota**: Disponível apenas em execução direta (não em executáveis compilados)

## Estrutura do Arquivo ETDX

O arquivo .etdx gerado contém:

```
documento.etdx (arquivo ZIP)
├── project.json          # Informações do projeto
├── master_template.json  # Template principal
├── page_list.json        # Lista de páginas
├── page_1/              # Pasta da página 1
│   ├── page_1.json      # Dados da página
│   └── page_1.jpg       # Imagem da página
├── page_2/              # Pasta da página 2
│   ├── page_2.json      # Dados da página
│   └── page_2.jpg       # Imagem da página
└── ...
```

## Cache

O sistema utiliza cache para otimizar o processamento:

- **Cache do modelo**: Armazena resultados do RealESRGAN
- **Cache final**: Armazena imagens processadas
- **Limpeza automática**: Cache é limpo ao sair do programa

## Limitações

1. **Executáveis compilados**: Upscale inteligente não está disponível
2. **Memória**: PDFs muito grandes podem consumir muita memória
3. **Tempo**: Processamento pode ser lento para PDFs com muitas páginas

## Troubleshooting

### Erro: "RealESRGAN não disponível"
- Instale as dependências de IA: `pip install py-real-esrgan`
- Verifique se o PyTorch está instalado corretamente

### Erro: "Arquivo PDF não encontrado"
- Verifique se o caminho do arquivo está correto
- Certifique-se de que o arquivo tem extensão .pdf

### Performance lenta
- Reduza o DPI para 300
- Use formato JPEG em vez de PNG
- Desabilite o upscale inteligente

## Exemplos de Uso

### Conversão simples
```bash
python etdx_cli.py relatorio.pdf
```

### Conversão com alta qualidade
```bash
python etdx_cli.py apresentacao.pdf --dpi 600 --format png --upscale
```

### Conversão em lote (script)
```bash
for file in *.pdf; do
    python etdx_cli.py "$file" --output "${file%.pdf}.etdx"
done
```

## Integração com o Sistema Existente

Este módulo é totalmente compatível com o sistema de geração de PDF existente:

- Usa a mesma estrutura de cache
- Compatível com multiprocessing
- Segue os mesmos padrões de código
- Integrado ao package `pdf_generator` 
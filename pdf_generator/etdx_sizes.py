# Tamanhos ETDX baseados nos exemplos
ETDX_SIZES = [
    {"id": "3.5x5", "label": "3,5 x 5 pol. (89 x 127 mm)", "paperSizeId": "LB", "size": [1332, 1912]},
    {"id": "4x6",   "label": "4 x 6 pol. (102 x 152 mm)", "paperSizeId": "KG", "size": [1512, 2272]},
    {"id": "5x7",   "label": "5 x 7 pol. (127 x 178 mm)", "paperSizeId": "2L", "size": [1872, 2634]},
    {"id": "8x10",  "label": "8 x 10 pol. (203 x 254 mm)", "paperSizeId": "6G", "size": [2952, 3712]},
    {"id": "A4",    "label": "A4 (210 x 297 mm)", "paperSizeId": "A4", "size": [3048, 4321]},
    {"id": "Carta", "label": "Carta (216 x 279 mm)", "paperSizeId": "LT", "size": [3132, 4072]},
    {"id": "Oficio","label": "Oficio (216 x 356 mm)", "paperSizeId": "LG", "size": [3132, 5152]},
]

def get_etdx_size_by_id(size_id):
    for s in ETDX_SIZES:
        if s["id"].lower() == size_id.lower():
            return s
    return None

def get_etdx_size_by_paperSizeId(paperSizeId):
    for s in ETDX_SIZES:
        if s["paperSizeId"].lower() == paperSizeId.lower():
            return s
    return None

def find_closest_etdx_size(width_mm, height_mm):
    mm_sizes = [
        ("3.5x5", 89, 127),
        ("4x6", 102, 152),
        ("5x7", 127, 178),
        ("8x10", 203, 254),
        ("A4", 210, 297),
        ("Carta", 216, 279),
        ("Oficio", 216, 356),
    ]
    # 1. Procurar o menor tamanho que caiba o PDF, considerando rotação
    candidates = []
    for size_id, w, h in mm_sizes:
        if (w >= width_mm and h >= height_mm) or (h >= width_mm and w >= height_mm):
            candidates.append((size_id, w, h))
    if candidates:
        # Escolher o menor em área
        best = min(candidates, key=lambda x: x[1]*x[2])
        return get_etdx_size_by_id(best[0])
    # 2. Se não couber em nenhum, usar o mais próximo por diferença absoluta
    best = None
    min_diff = float('inf')
    for size_id, w, h in mm_sizes:
        diff1 = abs(width_mm - w) + abs(height_mm - h)
        diff2 = abs(width_mm - h) + abs(height_mm - w)
        diff = min(diff1, diff2)
        if diff < min_diff:
            min_diff = diff
            best = size_id
    return get_etdx_size_by_id(best)

def get_etdx_label_by_paperSizeId(paperSizeId):
    for s in ETDX_SIZES:
        if s["paperSizeId"].lower() == paperSizeId.lower():
            return s["label"]
    return paperSizeId

def calculate_image_scale_and_position(paper_size_px, image_size_px, mode="fit", margin_mm=2.5):
    """
    Calcula a escala e posição da imagem no papel ETDX
    
    Args:
        paper_size_px: [width, height] do papel em pixels
        image_size_px: [width, height] da imagem em pixels
        mode: "fit" (ajustar) ou "fill" (preencher)
        margin_mm: margem em mm (padrão 2.5mm)
    
    Returns:
        dict com scale, center, crop
    """
    # Converter margem de mm para pixels (aproximadamente 14.5 pixels por mm)
    margin_px = int(margin_mm * 14.5)
    
    # Área disponível para a imagem (papel menos margens)
    available_width = paper_size_px[0] - (2 * margin_px)
    available_height = paper_size_px[1] - (2 * margin_px)
    
    # Proporções
    paper_ratio = available_width / available_height
    image_ratio = image_size_px[0] / image_size_px[1]
    
    if mode == "fit":
        # Modo Ajustar: imagem cabe completamente dentro da área disponível
        scale_x = available_width / image_size_px[0]
        scale_y = available_height / image_size_px[1]
        scale = min(scale_x, scale_y)  # Usar a menor escala para caber completamente
    else:  # mode == "fill"
        # Modo Preencher: imagem preenche a área disponível (pode cortar)
        scale_x = available_width / image_size_px[0]
        scale_y = available_height / image_size_px[1]
        scale = max(scale_x, scale_y)  # Usar a maior escala para preencher
    
    # Calcular tamanho da imagem escalada
    scaled_width = int(image_size_px[0] * scale)
    scaled_height = int(image_size_px[1] * scale)
    
    # Centralizar a imagem
    center_x = 0.0  # Centralizado horizontalmente
    center_y = 0.0  # Centralizado verticalmente
    
    # Calcular crop se necessário (para modo fill)
    crop_rect = [0, 0, image_size_px[0], image_size_px[1]]
    
    return {
        "scale": scale,
        "center": [center_x, center_y],
        "crop": {
            "type": 1,
            "rect": crop_rect
        }
    }

def calculate_image_scale_and_position_exact(paper_size_px, image_size_px, mode="fit"):
    """
    Calcula a escala e posição da imagem usando valores calibrados dos exemplos
    """
    # Valores calibrados baseados nos exemplos referencia.etdx e referencia_2.etdx
    # Para papel 5x7 (1872x2634) e imagem 1299x1951:
    # - Modo fit: scale = 1.2501514
    # - Modo fill: scale = 1.29376137
    
    # Calcular fator de calibração
    reference_paper = [1872, 2634]
    reference_image = [1299, 1951]
    reference_fit_scale = 1.2501514
    reference_fill_scale = 1.29376137
    
    # Calcular proporção da área disponível
    def get_scale_factor(paper, image, target_scale):
        # Área do papel
        paper_area = paper[0] * paper[1]
        # Área da imagem
        image_area = image[0] * image[1]
        # Proporção
        area_ratio = paper_area / image_area
        # Fator de calibração
        calibration_factor = target_scale / (area_ratio ** 0.5)
        return calibration_factor
    
    # Calcular fatores de calibração
    fit_calibration = get_scale_factor(reference_paper, reference_image, reference_fit_scale)
    fill_calibration = get_scale_factor(reference_paper, reference_image, reference_fill_scale)
    
    # Aplicar aos dados atuais
    current_paper_area = paper_size_px[0] * paper_size_px[1]
    current_image_area = image_size_px[0] * image_size_px[1]
    current_area_ratio = current_paper_area / current_image_area
    
    if mode == "fit":
        scale = (current_area_ratio ** 0.5) * fit_calibration
    else:  # mode == "fill"
        scale = (current_area_ratio ** 0.5) * fill_calibration
    
    return {
        "scale": scale,
        "center": [0.0, 0.0],
        "crop": {
            "type": 1,
            "rect": [0, 0, image_size_px[0], image_size_px[1]]
        }
    } 
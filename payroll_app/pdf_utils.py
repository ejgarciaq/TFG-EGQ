import io
import logging
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# =========================================================================
# LÓGICA DE BÚSQUEDA DEL LOGO ORIGINAL
# =========================================================================
def buscar_ruta_imagen():
    dir_actual = Path(__file__).resolve().parent
    for _ in range(5):
        posible_ruta = dir_actual / "static" / "img" / "logo.webp"
        if posible_ruta.exists():
            return posible_ruta
        dir_actual = dir_actual.parent
    return Path("static/img/logo.webp")

IMAGE_RELATIVE_PATH = buscar_ruta_imagen()

# =========================================================================
# CANVAS PERSONALIZADO PARA CONTAR Y DIBUJAR PÁGINAS (Página X de Y)
# =========================================================================
class NumeracionPaginasCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paginas = []

    def showPage(self):
        self.paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_total_paginas = len(self.paginas)
        for pagina in self.paginas:
            self.__dict__.update(pagina)
            self.draw_page_number(num_total_paginas)
            super().showPage()
        super().save()

    def draw_page_number(self, total_paginas):
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#4a5568"))
        texto = f"Página {self._pageNumber} de {total_paginas}"
        self.drawRightString(letter[0] - 40, 30, texto)

# =========================================================================
# FUNCIÓN PRINCIPAL DE GENERACIÓN DEL PDF
# =========================================================================
def build_pdf_from_rows(title, rows, metadata=None, headers=None):
    """
    Genera un archivo PDF con un tamaño de letra más pequeño (8) y fuerza
    a que las columnas se ajusten estrictamente al tamaño de su contenido.
    """
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=50
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20
    )
    
    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14
    )

    # LETRA MÁS PEQUEÑA (Tamaño 8, Leading 10)
    cell_header_style = ParagraphStyle(
        'CellHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.black
    )
    
    cell_body_style = ParagraphStyle(
        'CellBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.black
    )

    # 1. CABECERA: Título y Logo
    header_elements = []
    if IMAGE_RELATIVE_PATH.exists():
        try:
            logo = Image(str(IMAGE_RELATIVE_PATH), width=60, height=25)
            logo.hAlign = 'LEFT'
            header_elements.append(logo)
        except Exception as img_err:
            logging.error(f"No se pudo cargar la imagen pequeña del logo: {img_err}")
            header_elements.append("")
    else:
        header_elements.append("")

    header_elements.append(Paragraph(str(title), title_style))
    
    header_table = Table([header_elements], colWidths=[70, 462])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    
    story.append(header_table)
    story.append(Spacer(1, 10))
    
    # 2. Agregar Metadatos
    if metadata and isinstance(metadata, dict):
        for key, val in metadata.items():
            meta_text = f"<b>{key}:</b> {val}"
            story.append(Paragraph(meta_text, meta_style))
        story.append(Spacer(1, 15))
    
    # 3. Limpieza y Construcción de los Datos (Uso de 'C/')
    table_data = []
    
    if headers:
        cleaned_headers = [Paragraph(str(h).replace('₡', 'C/'), cell_header_style) for h in headers]
        table_data.append(cleaned_headers)
    
    for row in rows:
        processed_row = []
        for cell in row:
            if cell is None:
                cell_text = 'N/A'
            else:
                cell_text = str(cell).replace('₡', 'C/')
            processed_row.append(Paragraph(cell_text, cell_body_style))
        table_data.append(processed_row)
            
    # 4. AJUSTE ESTRICTO DE LAS COLUMNAS AL CONTENIDO REAL
    if table_data:
        num_cols = len(table_data[0])
        max_total_width = 532.0  # Límite máximo horizontal de la página
        
        col_widths = [0.0] * num_cols
        
        # Al ser tamaño 8, cada carácter ocupa aproximadamente 5.0 puntos en Helvetica
        for row in rows:
            for idx, cell in enumerate(row):
                val_str = str(cell) if cell is not None else 'N/A'
                display_str = val_str.replace('₡', 'C/')
                # Factor optimizado a 5.0 por el tamaño 8 + 12 puntos de padding de celdas
                estimated_width = len(display_str) * 5.0 + 12
                if estimated_width > col_widths[idx]:
                    col_widths[idx] = estimated_width
        
        if headers:
            for idx, h in enumerate(headers):
                estimated_h_width = len(str(h).replace('₡', 'C/')) * 5.0 + 12
                if estimated_h_width > col_widths[idx]:
                    col_widths[idx] = estimated_h_width

        # Control de desbordamiento: Solo reduce si la tabla completa es más ancha que la página.
        # Ya no se "rellena" el espacio sobrante si el contenido es corto, manteniendo las columnas ceñidas al texto.
        total_estimated = sum(col_widths)
        if total_estimated > max_total_width:
            col_widths = [(w / total_estimated) * max_total_width for w in col_widths]

        # 5. Inicialización de la Tabla
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.hAlign = 'LEFT'  # Alinea la tabla ceñida a la izquierda de la página si es angosta
        
        t_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),  # Padding más ajustado para letra pequeña
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ])
        
        t.setStyle(t_style)
        story.append(t)
    else:
        story.append(Paragraph("No hay registros disponibles.", styles['Normal']))
        
    try:
        doc.build(story, canvasmaker=NumeracionPaginasCanvas)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
    except Exception as e:
        logging.exception("Error técnico al compilar el reporte PDF en pdf_utils.py")
        raise e
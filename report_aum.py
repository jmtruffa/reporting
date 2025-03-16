import os
import sys
import re
from sqlalchemy import create_engine, text
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Image, Paragraph, PageBreak
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.lib.colors import HexColor

# Load environment variables
db_user = os.environ.get('POSTGRES_USER')
db_password = os.environ.get('POSTGRES_PASSWORD')
db_host = os.environ.get('POSTGRES_HOST')
db_port = os.environ.get('POSTGRES_PORT', '5432')
db_name = os.environ.get('POSTGRES_DB')
DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

# Register fonts
pdfmetrics.registerFont(TTFont("MS Sans Serif", "./Microsoft Sans Serif.ttf"))
pdfmetrics.registerFont(TTFont("MS Sans Serif Bold", "./MS Sans Serif Bold.ttf"))

# Database engine (global for reuse)
engine = create_engine(DATABASE_URL)

def read_procedures_from_file(filename):
    """Reads procedure names from a file, ignoring empty lines and comments."""
    procedures = []
    try:
        with open(filename, "r") as file:
            for line in file:
                proc_name = line.strip()
                if proc_name and not proc_name.startswith("#"):
                    procedures.append(proc_name)
    except FileNotFoundError:
        print(f"Error: El archivo '{filename}' no fue encontrado.")
        sys.exit(1)
    except Exception as e:
        print(f"Error leyendo el archivo de procedimientos: {e}")
        sys.exit(1)
    return procedures

def execute_procedure(engine, procedure_name):
    """Executes a PostgreSQL stored procedure with autocommit enabled."""
    with engine.connect() as connection:
        try:
            print(f"Iniciando ejecución de procedimiento {procedure_name} a las {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            connection.execution_options(isolation_level="AUTOCOMMIT")
            connection.execute(text(f"CALL {procedure_name}();"))
            print(f"El procedimiento {procedure_name} se ejecutó exitosamente a las {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
        except Exception as e:
            print(f"Error executing procedure {procedure_name}: {e}")

def add_header_footer(canvas, doc):
    """Adds header with logo, title including fecha, and footer with page number."""
    canvas.saveState()
    canvas.drawImage("./brand_logo.png", 40, 740, width=100, height=45)
    canvas.setFont("MS Sans Serif", 10)
    fecha_value = getattr(doc, 'fecha_value', 'N/A')
    canvas.drawString(160, 760, f"REPORTE DE AUM POR FONDO (cifras en millones). Información al: {fecha_value}")
    canvas.restoreState()

    canvas.saveState()
    canvas.setFont("MS Sans Serif", 10)
    canvas.drawString(40, 15, f"Generado por Outlier. Fecha:{datetime.now().strftime('%Y-%m-%d')} - Página {doc.page}")
    canvas.restoreState()

# Sub-Report 1: AUM Table (your current report)
def sub_report_aum_table():
    """Generates a table-based sub-report from report_aum_familia."""
    elements = []
    styles = getSampleStyleSheet()

    # Query database
    with engine.connect() as connection:
        query = text("""
            SELECT fecha_imputada AS FECHA, familia AS FAMILIA, categoria AS CATEGORIA,
                   "subCategoria" AS "Sub Categoria", patrimonio AS PATRIMONIO, gerente
            FROM report_aum_familia
            WHERE fecha_imputada = '2025-03-13'
        """)
        result = connection.execute(query)
        data = result.fetchall()
    
    # Title with dynamic data
    fecha_value = str(data[0][0]) if data else "N/A"
    total_aum = sum(float(row[4]) for row in data) / 1e6 if data else 0
    title = Paragraph(f"AUM por Fondo - Fecha: {fecha_value} (Total: {total_aum:,.0f} millones)", styles['Heading2'])
    elements.append(title)
    elements.append(Spacer(1, 10))

    # Table setup
    column_names = ["FAMILIA", "CATEGORIA", "SUB CATEGORIA", "AUM", "SOC. GERENTE"]
    wrap_style = ParagraphStyle(
        name='WrapStyle',
        fontName='MS Sans Serif',
        fontSize=6,
        textColor=colors.black,
        alignment=1,
        wordWrap='CJK',
        leading=7
    )

    table_data = [column_names]
    for row in data:
        aum = "{:,.0f}".format(float(row[4]) / 1e6).replace(",", ".")
        soc_gerente = re.sub(r'\s*[A-Z\.]+$', '', str(row[5])).strip()
        formatted_row = [
            Paragraph(str(row[1]), wrap_style),
            Paragraph(str(row[2]), wrap_style),
            Paragraph(str(row[3]), wrap_style),
            Paragraph(aum, wrap_style),
            Paragraph(soc_gerente, wrap_style)
        ]
        table_data.append(formatted_row)

    col_widths = [135, 75, 135, 60, 147]
    table = Table(table_data, colWidths=col_widths, hAlign='LEFT', repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'MS Sans Serif'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (1, 1), (-1, -1), 'MS Sans Serif'),
        ('FONTSIZE', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 0.05),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 0.05),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(table)
    elements.append(PageBreak())
    return elements

# Sub-Report 2: Example with Text and Table
from reportlab.platypus import Paragraph, Spacer, Table, PageBreak
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.colors import HexColor

def sub_report_summary():
    """Generates a sub-report with text, summary table, and minimal line chart."""
    elements = []
    styles = getSampleStyleSheet()

    # Query database (100 rows)
    with engine.connect() as connection:
        query = text("""
            SELECT fecha_imputada, SUM(patrimonio) AS total_aum
            FROM report_aum_familia
            GROUP BY fecha_imputada
            ORDER BY fecha_imputada DESC
            LIMIT 100
        """)
        result = connection.execute(query)
        data = result.fetchall()

    if not data:
        elements.append(Paragraph("No data available for Summary report.", styles['Normal']))
        elements.append(PageBreak())
        return elements

    print("Summary: Fetched", len(data), "rows")

    # Text introduction
    intro = Paragraph("Resumen de AUM por Fecha (Últimos 100 Días)", styles['Heading2'])
    elements.append(intro)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("A continuación, se presenta un resumen del patrimonio total por fecha, seguido de un gráfico.", styles['Normal']))
    elements.append(Spacer(1, 5))

    # Summary table
    table_data = [["Fecha", "Total AUM (millones)"]]
    for row in data:
        aum = "{:,.0f}".format(float(row[1]) / 1e6).replace(",", ".")
        table_data.append([str(row[0]), aum])
    
    table = Table(table_data, colWidths=[200, 200], hAlign='LEFT', repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'MS Sans Serif'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))
    print("Summary: Table added")

    # Minimal line chart
    try:
        drawing = Drawing(500, 200)
        line_chart = HorizontalLineChart()
        line_chart.x = 50
        line_chart.y = 50
        line_chart.width = 400
        line_chart.height = 100

        # Data
        chart_data = [[float(row[1]) / 1e6 for row in data]]
        line_chart.data = chart_data

        # Minimal setup
        line_chart.categoryAxis.visible = False
        line_chart.valueAxis.valueMin = 0
        line_chart.valueAxis.labels.fontName = 'MS Sans Serif'
        line_chart.valueAxis.labels.fontSize = 6
        line_chart.lines[0].strokeColor = HexColor('#FF6600')
        line_chart.lines[0].strokeWidth = 1

        drawing.add(line_chart)
        elements.append(drawing)
        print("Summary: Chart added")
    except Exception as e:
        print(f"Summary: Chart error: {str(e)}")
        elements.append(Paragraph(f"Chart failed: {str(e)}", styles['Normal']))

    elements.append(PageBreak())
    return elements

def generate_multi_report_pdf(output_file, sub_report_functions):
    """Generate a PDF with multiple sub-reports."""
    doc = SimpleDocTemplate(output_file, pagesize=letter, leftMargin=30, rightMargin=30, topMargin=80, bottomMargin=40)
    all_elements = []

    for func in sub_report_functions:
        report_name = func.__name__.replace('sub_report_', '').replace('_', ' ').title()
        try:
            print(f"Generating sub-report: {report_name}")
            sub_elements = func()
            if sub_elements:
                all_elements.extend(sub_elements)
                print(f"{report_name}: Elements added ({len(sub_elements)}): {[type(e).__name__ for e in sub_elements]}")
                for elem in sub_elements:
                    if isinstance(elem, Paragraph) and "Fecha:" in elem.text:
                        fecha_match = re.search(r"Fecha: (\S+)", elem.text)
                        if fecha_match:
                            doc.fecha_value = fecha_match.group(1)
                            print(f"{report_name}: Set doc.fecha_value to {doc.fecha_value}")
                            break
        except Exception as e:
            print(f"Error in sub-report '{report_name}': {str(e)}")
            styles = getSampleStyleSheet()
            error_style = styles['Normal']
            error_style.fontName = 'MS Sans Serif'
            all_elements.append(Paragraph(f"Error in {report_name}: {str(e)}", error_style))
            all_elements.append(PageBreak())

    print("All elements:", len(all_elements), [type(e).__name__ for e in all_elements])
    try:
        doc.build(all_elements, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
        print(f"Multi-report PDF generated: {output_file}")
    except Exception as e:
        print(f"Error during PDF build: {str(e)}")
        # Fixed filter: Explicitly include expected types
        safe_elements = [e for e in all_elements if type(e) in [Paragraph, Table, Spacer, PageBreak]]
        print("Safe elements:", len(safe_elements), [type(e).__name__ for e in safe_elements])
        if safe_elements:
            try:
                doc.build(safe_elements, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
                print(f"Minimal PDF generated: {output_file}")
            except Exception as e2:
                print(f"Minimal build failed: {str(e2)}")
        else:
            print("No safe elements to build PDF")

def main():
    # if len(sys.argv) != 2:
    #     print(f"Uso: {sys.argv[0]} /path/to/procedures_file")
    #     sys.exit(1)

    # procedure_file = sys.argv[1]
    # procedures = read_procedures_from_file(procedure_file)

    # if not procedures:
    #     print("No hay procedimientos especificados en el archivo. Saliendo.")
    #     sys.exit(1)

    # for proc in procedures:
    #     execute_procedure(engine, proc)

    # List of sub-report functions to include
    output_file = f"multi_report_aum_familia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    sub_reports = [sub_report_aum_table, sub_report_summary]  # Only Aum Table
    generate_multi_report_pdf(output_file, sub_reports)

if __name__ == "__main__":
    main()


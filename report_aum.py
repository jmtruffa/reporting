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
import matplotlib.pyplot as plt
import tempfile
import time

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
    canvas.drawString(160, 760, f"REPORTE DE FCI. Información al: {fecha_value}")
    canvas.restoreState()

    canvas.saveState()
    canvas.setFont("MS Sans Serif", 10)
    canvas.drawString(40, 15, f"Generado por Outlier. Fecha:{datetime.now().strftime('%Y-%m-%d')} - Página {doc.page}")
    canvas.restoreState()

def sub_report_efec_subcategoria(report_date):
    """Generates a sub-report with net subscription effects by subcategory."""
    elements = []
    styles = getSampleStyleSheet()

    # Query database with dynamic date
    with engine.connect() as connection:
        query = text("""
            SELECT 
                ei.fecha_imputada,
                cf."subCategoria",
                SUM(ROUND(ei.es_1d::numeric / 1e6, 0)) AS es_1d,
                SUM(ROUND(ei.es_1w::numeric / 1e6, 0)) AS es_1w,
                SUM(ROUND(ei.es_mtd::numeric / 1e6, 0)) AS es_mtd,
                SUM(ROUND(ei.es_1m::numeric / 1e6, 0)) AS es_1m,
                SUM(ROUND(ei.es_3m::numeric / 1e6, 0)) AS es_3m,
                SUM(ROUND(ei.es_ytd::numeric / 1e6, 0)) AS es_ytd,
                SUM(ROUND(ei.es_1y::numeric / 1e6, 0)) AS es_1y
            FROM efectos_intertemp ei
            JOIN "clasesFCI" cf ON ei.fondo = cf.fondo 
                AND (ei.fecha_imputada BETWEEN cf.desde AND COALESCE(cf.hasta, CURRENT_DATE))
            WHERE ei.fecha_imputada = :report_date
            GROUP BY ei.fecha_imputada, cf."subCategoria"
            ORDER BY es_1d
        """)
        result = connection.execute(query, {"report_date": report_date})
        data = result.fetchall()

    if not data:
        elements.append(Paragraph("No data available for Efectos Subcategoria report.", styles['Normal']))
        elements.append(PageBreak())
        return elements

    # Title
    title = Paragraph("EFECTOS DE SUSCRIPCION NETOS POR SUBCATEGORIA (en millones):", styles['Heading2'])
    elements.append(title)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"Fecha: {report_date}", styles['Normal']))
    elements.append(Spacer(1, 5))

    # Table
    table_data = [["SUB-CATEGORIA", "1D", "1SEM", "MTD", "1M", "3M", "YTD", "1Y"]]
    for row in data:
        table_data.append([
            row[1],  # subCategoria
            "{:,.0f}".format(row[2]).replace(",", "."),  # es_1d
            "{:,.0f}".format(row[3]).replace(",", "."),  # es_1w
            "{:,.0f}".format(row[4]).replace(",", "."),  # es_mtd
            "{:,.0f}".format(row[5]).replace(",", "."),  # es_1m
            "{:,.0f}".format(row[6]).replace(",", "."),  # es_3m
            "{:,.0f}".format(row[7]).replace(",", "."),  # es_ytd
            "{:,.0f}".format(row[8]).replace(",", ".")   # es_1y
        ])
    
    table = Table(table_data, colWidths=[150, 50, 50, 50, 50, 50, 50, 50], hAlign='LEFT', repeatRows=1)
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
    elements.append(PageBreak())
    
    print("Efectos Subcategoria: Table added")
    return elements

def sub_report_summary(report_date):
    """Generates a sub-report with text, summary table (newest first), and Matplotlib bar chart."""
    elements = []
    styles = getSampleStyleSheet()
    q_dias = 7  # 7 days

    # Query database (q_dias rows, newest first up to report_date)
    with engine.connect() as connection:
        query = text(f"""
            SELECT fecha_imputada, SUM(patrimonio) / 1e12 AS total_aum
            FROM report_aum_familia_2
            WHERE fecha_imputada <= :report_date
            GROUP BY fecha_imputada
            ORDER BY fecha_imputada DESC
            LIMIT {q_dias}
        """)
        result = connection.execute(query, {"report_date": report_date})
        data = result.fetchall()

    if not data:
        elements.append(Paragraph("No data available for Summary report.", styles['Normal']))
        elements.append(PageBreak())
        return elements

    print("Summary: Fetched", len(data), "rows")

    # Text introduction
    intro = Paragraph(f"AUM POR FECHA (Últimos {q_dias} Días)", styles['Heading2'])
    elements.append(intro)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("A continuación, se presenta un resumen del patrimonio total por fecha, seguido de un gráfico.", styles['Normal']))
    elements.append(Spacer(1, 5))

    # Summary table (newest first)
    table_data = [["Fecha", "Total AUM (billones)"]]
    for row in data:
        aum = "{:,.2f}".format(float(row[1])).replace(",", ".")
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

    # Matplotlib bar chart
    try:
        # Reverse data for chart (oldest first)
        fechas = [datetime.strptime(str(row[0]), '%Y-%m-%d') for row in data[::-1]]
        aum_values = [float(row[1]) for row in data[::-1]]
        print("Sample fechas:", [f.strftime('%m-%d') for f in fechas[:10]])

        # Use indices for x-axis to remove gaps
        x_indices = range(len(fechas))

        # Create bar plot
        plt.figure(figsize=(8, 4))
        plt.bar(x_indices, aum_values, color='#FF6600', width=0.8)
        plt.title("AUM Total por Fecha", fontsize=10)
        plt.xlabel("Fecha (MM-DD)", fontsize=8)
        plt.ylabel("AUM (billones)", fontsize=8)
        plt.xticks(x_indices, [f.strftime('%m-%d') for f in fechas], rotation=45, fontsize=6)  # Label with dates
        plt.yticks(fontsize=6)
        plt.ylim(0, max(aum_values) * 1.5)  # Y-axis max = 1.5x max value
        plt.grid(True, linestyle='--', alpha=0.7, axis='y')  # Grid only on y-axis
        plt.tight_layout()

        # Save to temp directory
        temp_dir = tempfile.gettempdir()
        chart_path = os.path.join(temp_dir, "temp_chart.png")
        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
        plt.close()

        # Verify file exists
        time.sleep(0.1)  # Ensure file is written
        if not os.path.exists(chart_path):
            raise FileNotFoundError(f"Chart file not created: {chart_path}")

        # Add to PDF, don’t delete here
        elements.append(Image(chart_path, width=400, height=200))
        print("Summary: Matplotlib chart added (path: %s)" % chart_path)

    except Exception as e:
        print(f"Summary: Chart error: {str(e)}")
        elements.append(Paragraph(f"Chart failed: {str(e)}", styles['Normal']))

    elements.append(PageBreak())
    return elements

def generate_multi_report_pdf(output_file, sub_report_functions, report_date):
    """Generate a PDF with multiple sub-reports, handle image cleanup."""
    doc = SimpleDocTemplate(output_file, pagesize=letter, leftMargin=30, rightMargin=30, topMargin=80, bottomMargin=40)
    all_elements = []
    image_paths = []

    for func in sub_report_functions:
        report_name = func.__name__.replace('sub_report_', '').replace('_', ' ').title()
        try:
            print(f"Generating sub-report: {report_name}")
            sub_elements = func(report_date)  # Pass report_date to sub-reports
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
                    if isinstance(elem, Image):
                        image_paths.append(elem.filename)
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
        safe_types = (Paragraph, Table, Spacer, PageBreak, Image)
        safe_elements = [e for e in all_elements if type(e) in safe_types]
        print("Safe types:", [t.__name__ for t in safe_types])
        print("All element types:", [type(e).__name__ for e in all_elements])
        print("Safe elements:", len(safe_elements), [type(e).__name__ for e in safe_elements])
        if safe_elements:
            try:
                doc.build(safe_elements, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
                print(f"Minimal PDF generated: {output_file}")
            except Exception as e2:
                print(f"Minimal build failed: {str(e2)}")
        else:
            print("No safe elements to build PDF")

    for path in image_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Cleaned up: {path}")
            except Exception as e:
                print(f"Failed to clean up {path}: {str(e)}")

def get_report_date():
    """Get report date from command-line argument or database."""
    if len(sys.argv) > 1:
        try:
            report_date = datetime.strptime(sys.argv[1], '%Y-%m-%d').date().isoformat()
            print(f"Using report date from argument: {report_date}")
            return report_date
        except ValueError:
            print(f"Invalid date format in argument '{sys.argv[1]}'. Fetching from database.")
    
    # Fetch max date from fci_diaria_2
    with engine.connect() as connection:
        query = text("SELECT MAX(fecha_imputada) FROM fci_diaria_2")
        result = connection.execute(query).scalar()
        report_date = result.isoformat() if result else '2025-03-13'  # Fallback
        print(f"Using report date from database: {report_date}")
        return report_date

def sub_report_efec_categoria(report_date):
    """Generates a sub-report with net subscription effects by category."""
    elements = []
    styles = getSampleStyleSheet()

    # Query database with dynamic date
    with engine.connect() as connection:
        query = text("""
            SELECT 
                ei.fecha_imputada,
                cf.categoria,
                SUM(ROUND(ei.es_1d::numeric / 1e6, 0)) AS es_1d,
                SUM(ROUND(ei.es_1w::numeric / 1e6, 0)) AS es_1w,
                SUM(ROUND(ei.es_mtd::numeric / 1e6, 0)) AS es_mtd,
                SUM(ROUND(ei.es_1m::numeric / 1e6, 0)) AS es_1m,
                SUM(ROUND(ei.es_3m::numeric / 1e6, 0)) AS es_3m,
                SUM(ROUND(ei.es_ytd::numeric / 1e6, 0)) AS es_ytd,
                SUM(ROUND(ei.es_1y::numeric / 1e6, 0)) AS es_1y
            FROM efectos_intertemp ei
            JOIN "clasesFCI" cf ON ei.fondo = cf.fondo 
                AND (ei.fecha_imputada BETWEEN cf.desde AND COALESCE(cf.hasta, CURRENT_DATE))
            WHERE ei.fecha_imputada = :report_date
            GROUP BY ei.fecha_imputada, cf.categoria
            ORDER BY es_1d
        """)
        result = connection.execute(query, {"report_date": report_date})
        data = result.fetchall()

    if not data:
        elements.append(Paragraph("No data available for Efectos Categoria report.", styles['Normal']))
        elements.append(PageBreak())
        return elements

    # Title
    title = Paragraph("EFECTOS DE SUSCRIPCION NETOS POR CATEGORIA (en millones):", styles['Heading2'])
    elements.append(title)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"Fecha: {report_date}", styles['Normal']))
    elements.append(Spacer(1, 5))

    # Table (excluding fecha_imputada)
    table_data = [["CATEGORIA", "1D", "1SEM", "MTD", "1M", "3M", "YTD", "1Y"]]
    for row in data:
        table_data.append([
            row[1],  # categoria -> CATEGORIA
            "{:,.0f}".format(row[2]).replace(",", "."),  # es_1d -> 1D
            "{:,.0f}".format(row[3]).replace(",", "."),  # es_1w -> 1SEM
            "{:,.0f}".format(row[4]).replace(",", "."),  # es_mtd -> MTD
            "{:,.0f}".format(row[5]).replace(",", "."),  # es_1m -> 1M
            "{:,.0f}".format(row[6]).replace(",", "."),  # es_3m -> 3M
            "{:,.0f}".format(row[7]).replace(",", "."),  # es_ytd -> YTD
            "{:,.0f}".format(row[8]).replace(",", ".")   # es_1y -> 1Y
        ])
    
    table = Table(table_data, colWidths=[150, 50, 50, 50, 50, 50, 50, 50], hAlign='LEFT', repeatRows=1)
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
    elements.append(PageBreak())
    
    print("Efectos Categoria: Table added")
    return elements

def main():
    report_date = get_report_date()
    output_file = f"multi_report_aum_familia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    sub_reports = [
        sub_report_efec_subcategoria,  # First
        sub_report_efec_categoria,     # Second
        sub_report_summary             # Third
    ]
    generate_multi_report_pdf(output_file, sub_reports, report_date)

if __name__ == "__main__":
    main()
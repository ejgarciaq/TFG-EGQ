from flask import Blueprint, current_app, request, render_template, flash, redirect, url_for, send_file
from ..models import Empleado, RegistroAsistencia
from weasyprint import HTML, CSS
from flask import send_file, request
from payroll_app.models import db
from datetime import datetime
import pandas as pd
import io

reportes_bp = Blueprint('reportes_bp', __name__)


@reportes_bp.route('/asistencia', methods=['GET'])
def mostrar_pagina_reporte():
    """Renderiza la página del formulario para generar reportes."""
    empleados = Empleado.query.all()
    return render_template(
        'rp_asistencia.html',
        empleados=empleados,
        empleado_id_seleccionado='todos',
        fecha_inicio_seleccionada='',
        fecha_fin_seleccionada=''
    )


@reportes_bp.route('/reportes/generar', methods=['POST'])
def generar_reporte():
    """Procesa el formulario y genera el reporte de asistencia."""
    try:
        # 1. Obtener los filtros del formulario
        empleado_id = request.form.get('empleado_id')
        fecha_inicio_str = request.form.get('fecha_inicio')
        fecha_fin_str = request.form.get('fecha_fin')
        descargar_formato = request.form.get('descargar')

        # 2. Validación de fechas
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

        if fecha_inicio > fecha_fin:
            flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'warning')
            return redirect(url_for('reportes_bp.mostrar_pagina_reporte'))
        
        # 3. Consulta a la base de datos
        query = db.session.query(RegistroAsistencia).filter(
            RegistroAsistencia.fecha_registro.between(fecha_inicio, fecha_fin)
        )
        if empleado_id != 'todos':
            query = query.filter_by(Empleado_id_empleado=empleado_id)
        
        registros = query.all()

        # 4. Manejo del caso sin registros
        if not registros:
            flash('No se encontraron registros de asistencia para los criterios de búsqueda seleccionados.', 'info')
            return redirect(url_for('reportes_bp.mostrar_pagina_reporte'))

        # 5. Lógica para generar y mostrar/descargar el reporte
        data = [{
            'Empleado': registro.empleado.nombre_completo if registro.empleado else 'N/A',
            'Fecha': registro.fecha_registro,
            'Hora Entrada': registro.hora_entrada,
            'Hora Salida': registro.hora_salida,
        } for registro in registros]
        df = pd.DataFrame(data)
        
        # Lógica de exportación a CSV
        if descargar_formato == 'csv':
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            
            return send_file(
                io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.csv'
            )
        
        # Lógica de exportación a Excel
        elif descargar_formato == 'excel':
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False, engine='openpyxl')
            excel_buffer.seek(0)
            
            return send_file(
                excel_buffer,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.xlsx'
            )

        # Lógica de exportación a PDF
        elif descargar_formato == 'pdf':

            # Crea una URL absoluta para el logo que WeasyPrint pueda seguir
            logo_url = url_for('static', filename='img/logo.webp', _external=True)

            # Genera la tabla HTML del reporte
            html_reporte = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Reporte de Asistencia</title>
                <link rel="stylesheet" href="{url_for('static', filename='css/reporte_asistencia.css')}">
            </head>
            <body>
                <div class="logo-container">
                    <img src="{logo_url}" alt="Logo de la empresa">
                </div>
                <h1>Reporte de Asistencia</h1>
                {df.to_html(classes='table table-striped')}
            </body>
            </html>
            """
            
            # Obtiene la ruta al archivo CSS para WeasyPrint
            css_path = current_app.root_path + url_for('static', filename='css/reporte_asistencia.css')

            pdf_buffer = io.BytesIO()

            # Pasa el HTML y el CSS a WeasyPrint para generar el PDF
            HTML(string=html_reporte).write_pdf(
                pdf_buffer, 
                stylesheets=[CSS(filename=css_path)]
            )

            pdf_buffer.seek(0)
            
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.pdf'
            )
        
        else:
            empleados = Empleado.query.all()
            return render_template(
                'rp_asistencia.html',
                empleados=empleados,
                reporte_html=df.to_html(classes='table table-striped'),
                empleado_id_seleccionado=empleado_id,
                fecha_inicio_seleccionada=fecha_inicio_str,
                fecha_fin_seleccionada=fecha_fin_str
            )
    except ValueError:
        flash('Formato de fecha inválido. Por favor, seleccione fechas del calendario.', 'danger')
        return redirect(url_for('reportes_bp.mostrar_pagina_reporte'))
    
    except Exception as e:
        print(f"Error al generar el reporte: {e}")
        flash('Ocurrió un error técnico al generar el reporte. Por favor, inténtelo de nuevo.', 'danger')
        return redirect(url_for('reportes_bp.mostrar_pagina_reporte'))


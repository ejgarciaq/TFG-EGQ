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

reportes_bp = Blueprint('reportes_bp', __name__)

@reportes_bp.route('/reportes/asistencia', methods=['GET'])
def mostrar_pagina_reporte():
    """Muestra la página inicial del formulario de reporte."""
    empleados = Empleado.query.all()
    # Pasa variables con valores predeterminados para evitar el error
    return render_template(
        'rp_asistencia.html',
        empleados=empleados,
        empleado_id_seleccionado='todos',
        fecha_inicio_seleccionada='',
        fecha_fin_seleccionada=''
    )

@reportes_bp.route('/asistencia/generar', methods=['GET', 'POST'])
def generar_reporte():
    """Procesa el formulario y genera/descarga el reporte de asistencia."""
    
    empleados = Empleado.query.all()
    reporte_html = None
    paginated_records = None
    
    # Obtener los valores del formulario o de los parámetros de la URL
    # Esto asegura que los filtros se mantengan al navegar por la paginación
    empleado_id_seleccionado = request.form.get('empleado_id', request.args.get('empleado_id', 'todos'))
    fecha_inicio_str = request.form.get('fecha_inicio', request.args.get('fecha_inicio', ''))
    fecha_fin_str = request.form.get('fecha_fin', request.args.get('fecha_fin', ''))
    descargar_formato = request.form.get('descargar', request.args.get('descargar', 'html')) # Por defecto, muestra HTML
    page = request.args.get('page', 1, type=int)

    # --- Lógica principal para generar el reporte ---
    # Esto se ejecutará si se enviaron fechas (ya sea por POST o en los parámetros de la URL)
    # y si no es una descarga directa a un formato diferente de HTML
    if fecha_inicio_str and fecha_fin_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

            if fecha_inicio > fecha_fin:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'warning')
                # Redirecciona a la misma página sin generar reporte, pero manteniendo filtros
                return redirect(url_for('reportes_bp.generar_reporte', 
                                        empleado_id=empleado_id_seleccionado, 
                                        fecha_inicio=fecha_inicio_str, 
                                        fecha_fin=fecha_fin_str, 
                                        descargar=descargar_formato))
            
            # --- CONSTRUCCIÓN DE LA CONSULTA (AHORA CON .join(Empleado) AQUÍ TAMBIÉN) ---
            base_query = db.session.query(RegistroAsistencia).join(Empleado).filter(
                RegistroAsistencia.fecha_registro.between(fecha_inicio, fecha_fin)
            ).order_by(RegistroAsistencia.fecha_registro.asc(), Empleado.nombre.asc())
            
            if empleado_id_seleccionado != 'todos':
                # Filtra por la clave foránea que está en RegistroAsistencia
                base_query = base_query.filter(RegistroAsistencia.Empleado_id_empleado == int(empleado_id_seleccionado))

            # --- Lógica de descarga o visualización en HTML ---
            if descargar_formato == 'html':
                registros_por_pagina = 10
                paginated_records = base_query.paginate(page=page, per_page=registros_por_pagina, error_out=False)
                registros = paginated_records.items
            else: # Para CSV, Excel, PDF, queremos todos los registros (sin paginación)
                registros = base_query.all()
            
            if not registros:
                flash('No se encontraron registros de asistencia para los criterios de búsqueda.', 'info')
                # Redirecciona a la misma página sin generar reporte, pero manteniendo filtros
                return redirect(url_for('reportes_bp.generar_reporte', 
                                        empleado_id=empleado_id_seleccionado, 
                                        fecha_inicio=fecha_inicio_str, 
                                        fecha_fin=fecha_fin_str, 
                                        descargar=descargar_formato))

            # Preparar los datos para Pandas
            data = [{
                'Empleado': registro.empleado.nombre_completo if registro.empleado else 'N/A',
                'Fecha': registro.fecha_registro,
                'Hora Entrada': registro.hora_entrada.strftime('%H:%M:%S') if registro.hora_entrada else 'N/A',
                'Salida Almuerzo': registro.hora_entrada_almuerzo.strftime('%H:%M:%S') if registro.hora_entrada_almuerzo else 'N/A',
                'Regreso Almuerzo': registro.hora_salida_almuerzo.strftime('%H:%M:%S') if registro.hora_salida_almuerzo else 'N/A',
                'Hora Salida': registro.hora_salida.strftime('%H:%M:%S') if registro.hora_salida else 'N/A',
                'Total Horas': f"{registro.total_horas:.2f}" if registro.total_horas is not None else '0.00',
                'Horas Extra': f"{registro.hora_extra:.2f}" if registro.hora_extra is not None else '0.00',
                'Horas Feriado': f"{registro.hora_feriado:.2f}" if registro.hora_feriado is not None else '0.00',
                'Aprobado': 'Sí' if registro.aprobacion_registro else 'No',
            } for registro in registros]
            df = pd.DataFrame(data)

            # Lógica de descarga y generación de HTML
            if descargar_formato == 'html':
                reporte_html = df.to_html(classes='table table-striped table-bordered table-hover mt-3', index=False)
            
            elif descargar_formato == 'csv':
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                csv_buffer.seek(0)
                return send_file(
                    io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
                    mimetype='text/csv',
                    as_attachment=True,
                    download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.csv'
                )
            
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

            elif descargar_formato == 'pdf':
                logo_url = url_for('static', filename='img/logo.webp', _external=True)
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
                    {df.to_html(classes='table table-striped table-bordered', index=False)}
                </body>
                </html>
                """
                css_path = current_app.root_path + url_for('static', filename='css/reporte_asistencia.css')
                pdf_buffer = io.BytesIO()
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

        except ValueError:
            flash('Formato de fecha inválido. Por favor, seleccione fechas del calendario.', 'danger')
        
        except Exception as e:
            print(f"Error al generar el reporte: {e}")
            flash('Ocurrió un error técnico al generar el reporte. Por favor, inténtelo de nuevo.', 'danger')
            
    # Renderiza la página final con el reporte HTML o solo el formulario
    # Esta es la ruta de salida única para todos los render_template
    return render_template(
        'rp_asistencia.html',
        empleados=empleados,
        empleado_id_seleccionado=empleado_id_seleccionado,
        fecha_inicio_seleccionada=fecha_inicio_str,
        fecha_fin_seleccionada=fecha_fin_str,
        reporte_html=reporte_html,
        paginated_records=paginated_records
    )


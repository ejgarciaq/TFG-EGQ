import csv, io, logging, os
from flask import ( Blueprint, current_app, make_response, request, render_template, flash, redirect, url_for, send_file )
from flask_login import login_required
from sqlalchemy import extract
from payroll_app.models import Aguinaldo, Liquidacion, db, Empleado, RegistroAsistencia, Nomina, TipoNomina
from weasyprint import HTML, CSS
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import joinedload, aliased
from payroll_app.routes.decorators import permiso_requerido

""" Rutas y lógica para generación de reportes en varios formatos (HTML, CSV, Excel, PDF)."""
reportes_bp = Blueprint('reportes_bp', __name__)


# FUNCIÓN AUXILIAR PARA LA GENERACIÓN DE ARCHIVOS EN SEGUNDO PLANO
def generate_file_in_thread(df_download, format, filename):
    """
    Genera el archivo CSV/Excel/PDF en un hilo separado 
    y lo guarda en una ubicación temporal.
    """
    temp_dir = os.path.join(current_app.root_path, 'temp_downloads')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        
    filepath = os.path.join(temp_dir, filename)

    try:
        if format == 'csv':
            df_download.to_csv(filepath, index=False)
        elif format == 'excel':
            df_download.to_excel(filepath, index=False, engine='openpyxl')
        elif format == 'pdf':
            # Nota: Esto asume que tienes todo el código de weasyprint disponible
            from weasyprint import HTML, CSS 
            html_reporte_pdf = "..." # Reconstruye tu HTML para el PDF aquí
            css_path = os.path.join(current_app.root_path, 'static', 'css', 'reportes.css')
            HTML(string=html_reporte_pdf).write_pdf(filepath, stylesheets=[CSS(filename=css_path)])
            
        print(f"Archivo '{filename}' generado con éxito en: {filepath}")

    except Exception as e:
        print(f"Error en el hilo al generar el archivo {filename}: {e}")
        # Aquí deberías manejar el error, quizás loggeándolo o notificando al usuario.

"""Renderiza la página del formulario para generar reportes."""
@reportes_bp.route('/asistencia', methods=['GET'])
@permiso_requerido('rp_asistencia')
@login_required # Proteger esta ruta con login y roles si es necesario
def mostrar_pagina_reporte():
    empleados = Empleado.query.all()
    return render_template( 
        'reporte/rp_asistencia.html',
        empleados=empleados,
        empleado_id_seleccionado='todos',
        fecha_inicio_seleccionada='',
        fecha_fin_seleccionada='' )

""" Genera y descarga el reporte de asistencia en el formato solicitado."""
@reportes_bp.route('/asistencia', methods=['GET', 'POST'])
@permiso_requerido('rp_asistencia')
@login_required # Proteger esta ruta con login y roles si es necesario
def generar_reporte():
    
    empleados = Empleado.query.all()
    reporte_html = None
    
    # --- 1. OBTENER PARÁMETROS ---
    empleado_id_seleccionado = request.form.get('empleado_id', request.args.get('empleado_id', 'todos'))
    fecha_inicio_str = request.form.get('fecha_inicio', request.args.get('fecha_inicio', ''))
    fecha_fin_str = request.form.get('fecha_fin', request.args.get('fecha_fin', ''))
    descargar_formato = request.form.get('descargar', request.args.get('descargar', 'html')) 
    
    # Flag para saber si se intenta una descarga
    is_download_request = descargar_formato in ['csv', 'excel', 'pdf']
    
    # --- 2. LÓGICA DE REPORTE ---
    if fecha_inicio_str and fecha_fin_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

            if fecha_inicio > fecha_fin:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'warning')
            else:
                # --- CONSTRUCCIÓN DE LA CONSULTA BASE (Se mantiene) ---
                base_query = db.session.query(RegistroAsistencia).join(Empleado).filter(
                    RegistroAsistencia.fecha_registro.between(fecha_inicio, fecha_fin)
                ).order_by(RegistroAsistencia.fecha_registro.asc(), Empleado.nombre.asc())
                
                if empleado_id_seleccionado != 'todos':
                    base_query = base_query.filter(RegistroAsistencia.Empleado_id_empleado == int(empleado_id_seleccionado))

                # Obtener todos los registros de una vez
                registros = base_query.all()
                
                if registros:
                    # Generación de la DATA (necesaria para la vista y la descarga)
                    data = [{
                        'Empleado': registro.empleado.nombre_completo if registro.empleado else 'N/A',
                        'Fecha': registro.fecha_registro,
                        'Hora Entrada': registro.hora_entrada.strftime('%I:%M:%S %p') if registro.hora_entrada else 'N/A',
                        'Salida Almuerzo': registro.hora_salida_almuerzo.strftime('%I:%M:%S %p') if registro.hora_salida_almuerzo else 'N/A',
                        'Regreso Almuerzo': registro.hora_entrada_almuerzo.strftime('%I:%M:%S %p') if registro.hora_entrada_almuerzo else 'N/A',
                        'Hora Salida': registro.hora_salida.strftime('%I:%M:%S %p') if registro.hora_salida else 'N/A',
                        'Total Horas': f"{registro.total_horas:.2f}" if registro.total_horas is not None else '0.00',
                        'Horas Extra': f"{registro.hora_extra:.2f}" if registro.hora_extra is not None else '0.00',
                        'Horas Feriado': f"{registro.hora_feriado:.2f}" if registro.hora_feriado is not None else '0.00',
                        'Aprobado': 'Sí' if registro.aprobacion_registro else 'No',
                    } for registro in registros]
                    df_download = pd.DataFrame(data)
                    
                    # Generamos el HTML para la vista (solo si NO es una solicitud de descarga)
                    if not is_download_request:
                        reporte_html = df_download.to_html(classes='table table-striped table-bordered table-hover mt-3', index=False)
                    
                    # --- Lógica de descarga (SÍNCRONA) ---
                    if descargar_formato == 'csv':
                        csv_buffer = io.StringIO()
                        df_download.to_csv(csv_buffer, index=False)
                        csv_buffer.seek(0)
                        # Retorna el archivo directamente
                        return send_file(io.BytesIO(csv_buffer.getvalue().encode('utf-8')), 
                                         mimetype='text/csv', 
                                         as_attachment=True, 
                                         download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.csv')
                    
                    elif descargar_formato == 'excel':
                        excel_buffer = io.BytesIO()
                        df_download.to_excel(excel_buffer, index=False, engine='openpyxl')
                        excel_buffer.seek(0)
                        # Retorna el archivo directamente
                        return send_file(excel_buffer, 
                                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                                         as_attachment=True, 
                                         download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.xlsx')

                    elif descargar_formato == 'pdf':
                        from weasyprint import HTML, CSS 
                        
                        empleado_obj = Empleado.query.get(int(empleado_id_seleccionado)) if empleado_id_seleccionado.isdigit() else None
                        empleado_info = empleado_obj.nombre_completo if empleado_obj else 'Todos'
                        logo_url = url_for('static', filename='img/logo.webp', _external=True)

                        html_reporte_pdf = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Reporte de Asistencia</title></head><body>
                                                
                                                <div class="logo-container">
                                                    <img src="{logo_url}">
                                                </div>

                                                <div class="header-content-wrapper">
                                                    <h1>Reporte de Asistencia</h1>
                                                    <p><strong>Desde:</strong> {fecha_inicio_str} &nbsp;&nbsp; <strong>Hasta:</strong> {fecha_fin_str}</p>
                                                    <p><strong>Empleado:</strong> {empleado_info}</p>
                                                </div>
                                                
                                                {df_download.to_html(classes='table table-striped table-bordered', index=False)}
                                                </body></html>"""
                        
                        css_path = os.path.join(current_app.root_path, 'static', 'css', 'reportes.css')
                        pdf_buffer = io.BytesIO()
                        HTML(string=html_reporte_pdf).write_pdf(pdf_buffer, stylesheets=[CSS(filename=css_path)])
                        pdf_buffer.seek(0)
                        #  Retorna el archivo directamente 
                        return send_file(pdf_buffer, 
                                         mimetype='application/pdf', 
                                         as_attachment=True, 
                                         download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.pdf')
                    
                else:
                    # No hay registros en total
                    flash('No se encontraron registros de asistencia para los criterios de búsqueda.', 'info')
                    reporte_html = None 
                    
                # Si es una solicitud de descarga, pero no se pudo generar (ej. error interno), 
                # la función simplemente continúa para renderizar la página con el mensaje de error.

        except Exception as e:
            print(f"Error al generar el reporte: {e}")
            flash('Ocurrió un error técnico al generar el reporte. Por favor, inténtelo de nuevo.', 'danger')
            
    # --- 3. RENDERIZADO FINAL ---
    return render_template(
        'reporte/rp_asistencia.html',
        empleados=empleados,
        empleado_id_seleccionado=empleado_id_seleccionado,
        fecha_inicio_seleccionada=fecha_inicio_str,
        fecha_fin_seleccionada=fecha_fin_str,
        reporte_html=reporte_html,
    )

# ====================================================================
# --- REPORTE DE NOMINA ---
# ====================================================================

""" Rutas y lógica para generación de reportes de nómina en varios formatos (HTML, CSV, Excel, PDF)."""
@reportes_bp.route('/nomina', methods=['GET'])
@permiso_requerido('rp_nomina')
@login_required
def mostrar_pagina_reporte_nomina():
    """Renderiza la página del formulario y, si los filtros están presentes, la tabla de resultados."""
    
    # Parámetros del Formulario (desde la URL o redirección)
    tipos_nomina = TipoNomina.query.all()
    fecha_inicio_seleccionada = request.args.get('fecha_inicio', '')
    fecha_fin_seleccionada = request.args.get('fecha_fin', '')
    id_tipo_nomina_seleccionado = request.args.get('tipo_nomina_id', 'todos')
    
    # Por ahora, la mantenemos como la "página inicial"
    return render_template(
        'reporte/rp_nomina.html',
        tipos_nomina=tipos_nomina,
        fecha_inicio_seleccionada=fecha_inicio_seleccionada,
        fecha_fin_seleccionada=fecha_fin_seleccionada,
        id_tipo_nomina_seleccionado=id_tipo_nomina_seleccionado,
        tabla_nomina_html=None,
        paginated_records=None,
        tipo_nomina_nombre=None,
    )

""" Función auxiliar para formatear moneda en español."""
def format_currency_es(value):
    """Formatea un valor numérico a formato de moneda español (separador de miles: '.', decimal: ',')."""
    if value is None:
        return '₡ 0,00'  # Asegura el manejo de valores None o nulos
        
    if isinstance(value, (int, float)):
        # 1. Formatear con separador de miles por defecto y 2 decimales (ej: 1,234,567.89)
        # Usamos abs(value) para formatear el número sin signo (el signo se añade al final)
        formatted = f"{abs(value):,.2f}"
        
        # 2. Reemplazar ',' (separador de miles) por '#' temporalmente
        formatted = formatted.replace(",", "#")
        
        # 3. Reemplazar '.' (separador decimal) por ','
        formatted = formatted.replace(".", ",")
        
        # 4. Reemplazar '#' por '.' (separador de miles español)
        formatted = formatted.replace("#", ".")
        
        # 5. Determinar el signo (si es negativo)
        signo = '-' if value < 0 else ''

        # RETORNO FINAL: Incluir el signo de colón y el signo negativo (si aplica)
        return f"{signo}₡ {formatted}"
    
    return str(value)

""" Genera y descarga el reporte de nómina en el formato solicitado."""
@reportes_bp.route('/nomina/generar', methods=['GET']) 
@permiso_requerido('rp_nomina')
@login_required
def generar_reporte_nomina():
    """Procesa los filtros, genera el reporte (HTML o descarga) y gestiona errores."""
    
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    id_tipo_nomina_str = request.args.get('tipo_nomina_id', 'todos')
    descargar_formato = request.args.get('descargar', 'html')
    page = request.args.get('page', 1, type=int)

    # Si por alguna razón la URL se golpea sin fechas (aunque el formulario lo requiera)
    if not fecha_inicio_str or not fecha_fin_str:
        flash('Por favor, selecciona un rango de fechas para generar el reporte de nómina.', 'warning')
        # Redirecciona a la función de vista/formulario
        return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina')) 

    try:
        fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        # id_tipo_nomina_int = int(id_tipo_nomina_str) if id_tipo_nomina_str and id_tipo_nomina_str != 'todos' else None
        # Corregido para no usar 'and id_tipo_nomina_str' ya que se usa después.
        id_tipo_nomina_int = int(id_tipo_nomina_str) if id_tipo_nomina_str != 'todos' else None


        if fecha_inicio_obj > fecha_fin_obj:
            flash('La fecha de inicio no puede ser posterior a la fecha de fin para el reporte.', 'warning')
            # Redirecciona a la función de vista/formulario, manteniendo los filtros
            return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                                     fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str,
                                     tipo_nomina_id=id_tipo_nomina_str))

        # --- Consulta de las nóminas (Lógica de base de datos) ---
        EmpleadoAlias = aliased(Empleado)
        query_nominas = Nomina.query.options(
            joinedload(Nomina.empleado.of_type(EmpleadoAlias)), 
            joinedload(Nomina.tipo_nomina_relacion)
        ).filter(
            Nomina.fecha_inicio >= fecha_inicio_obj,
            Nomina.fecha_fin <= fecha_fin_obj
        )
        if id_tipo_nomina_int:
            query_nominas = query_nominas.filter(Nomina.TipoNomina_id_tipo_nomina == id_tipo_nomina_int)
        
        query_nominas = query_nominas.order_by(Nomina.fecha_creacion.desc())
        
        # --- LÓGICA DE VISUALIZACIÓN EN HTML (PAGINACIÓN) ---
        if descargar_formato == 'html':
            
            # Obtener datos para la vista
            tipos_nomina = TipoNomina.query.all()
            tipo_nomina_nombre = next(
                 (t.nombre_tipo for t in tipos_nomina if str(t.id_tipo_nomina) == id_tipo_nomina_str),
                 'Todos'
            )
            
            PER_PAGE = 10 
            paginated_records = query_nominas.paginate(page=page, per_page=PER_PAGE, error_out=False)
            nominas_reporte = paginated_records.items
            
            if not nominas_reporte and page == 1:
                flash('No se encontraron nóminas generadas para el reporte.', 'info')
                #  Redirecciona a la función de vista/formulario, manteniendo los filtros
                return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                                         fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str,
                                         tipo_nomina_id=id_tipo_nomina_str))

            # Preparar el DataFrame para la PÁGINA ACTUAL
            data_for_df = [{
                 "Nombre Completo": n.empleado.nombre_completo if n.empleado else 'N/A', 
                 "Cédula": n.empleado.cedula if n.empleado else 'N/A',
                 "Tipo de Nómina": n.tipo_nomina_relacion.nombre_tipo if n.tipo_nomina_relacion else 'N/A',
                 "Período de Nómina": f"{n.fecha_inicio.strftime('%Y-%m-%d')} a {n.fecha_fin.strftime('%Y-%m-%d')}",
                 "Salario Bruto": n.salario_bruto,
                 "Deducciones Totales": n.deducciones,
                 "Salario Neto": n.salario_neto,
                 "Fecha de Generación": n.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S')
            } for n in nominas_reporte]
            
            df = pd.DataFrame(data_for_df)
            
            # Formatear moneda y generar el HTML
            for col in ["Salario Bruto", "Deducciones Totales", "Salario Neto"]:
                 df[col] = df[col].apply(lambda x: format_currency_es(x) if isinstance(x, (int, float)) else x)

            tabla_html = df.to_html(classes='table table-striped table-bordered table-hover mt-3', index=False, border=0)

            #  Retorno final para MOSTRAR EN PANTALLA
            return render_template(
                'reporte/rp_nomina.html',
                tipos_nomina=tipos_nomina,
                fecha_inicio_seleccionada=fecha_inicio_str,
                fecha_fin_seleccionada=fecha_fin_str,
                id_tipo_nomina_seleccionado=id_tipo_nomina_str,
                tabla_nomina_html=tabla_html, # Pasa la tabla HTML
                paginated_records=paginated_records,
                tipo_nomina_nombre=tipo_nomina_nombre
            )

        # --- Lógica de descarga (CSV, Excel, PDF) ---
        else:
            # Obtener todos los registros para la descarga
            nominas_reporte_completo = query_nominas.all()
            
            if not nominas_reporte_completo:
                 flash(f'No se encontraron nóminas para descargar en formato {descargar_formato}.', 'info')
                 # Redirige a la función de vista/formulario, manteniendo los filtros
                 return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                                          fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str,
                                          tipo_nomina_id=id_tipo_nomina_str))

            data_for_df_completo = [{
                "Nombre Completo": n.empleado.nombre_completo if n.empleado else 'N/A', 
                "Cédula": n.empleado.cedula if n.empleado else 'N/A',
                "Tipo de Nómina": n.tipo_nomina_relacion.nombre_tipo if n.tipo_nomina_relacion else 'N/A',
                "Período de Nómina": f"{n.fecha_inicio.strftime('%Y-%m-%d')} a {n.fecha_fin.strftime('%Y-%m-%d')}",
                "Salario Bruto": n.salario_bruto,
                "Deducciones Totales": n.deducciones,
                "Salario Neto": n.salario_neto,
                "Fecha de Generación": n.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S')
            } for n in nominas_reporte_completo]
            df = pd.DataFrame(data_for_df_completo)
            
            # --- Descarga CSV ---
            if descargar_formato == 'csv':
                 for col in ["Salario Bruto", "Deducciones Totales", "Salario Neto"]:
                     df[col] = df[col].apply(format_currency_es)
                     
                 csv_buffer = io.StringIO()
                 df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                 csv_buffer.seek(0)
                 return send_file(
                     io.BytesIO(csv_buffer.getvalue().encode('utf-8-sig')),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=f'reporte_nomina_{fecha_inicio_str}_a_{fecha_fin_str}.csv'
                 )
                 
            # --- Descarga Excel ---
            elif descargar_formato == 'excel':
                 excel_buffer = io.BytesIO()
                 df.to_excel(excel_buffer, index=False, engine='openpyxl')
                 excel_buffer.seek(0)
                 return send_file(
                     excel_buffer,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name=f'reporte_nomina_{fecha_inicio_str}_a_{fecha_fin_str}.xlsx'
                 )
                 
            # --- Descarga PDF ---
            elif descargar_formato == 'pdf':
                # Nota: Necesitas asegurarte de que TipoNomina.query.all() esté disponible
                # y que weasyprint.HTML y weasyprint.CSS estén importados.
                
                # Obtener el nombre del tipo de nómina para el encabezado del PDF
                tipo_nomina_nombre_descarga = next(
                    (t.nombre_tipo for t in TipoNomina.query.all() if str(t.id_tipo_nomina) == id_tipo_nomina_str),
                    'Todos'
                )
                
                logo_url = url_for('static', filename='img/logo.webp', _external=True)
                css_path = os.path.join(current_app.root_path, 'static', 'css', 'reportes.css')
                
                # Aplicar formato de moneda antes de generar el HTML del PDF
                for col in ["Salario Bruto", "Deducciones Totales", "Salario Neto"]:
                    df[col] = df[col].apply(format_currency_es)

                html_reporte = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Reporte de Nómina</title>
                    <link rel="stylesheet" href="{url_for('static', filename='css/reportes.css', _external=True)}">
                </head>
                <body>
                    <div class="logo-container">
                        <img src="{logo_url}" alt="Logo de la empresa">
                    </div>
                    <h1>Reporte de Nómina</h1>
                    <p><strong>Período:</strong> {fecha_inicio_str} a {fecha_fin_str}</p>
                    <p><strong>Tipo de Nómina:</strong> {tipo_nomina_nombre_descarga}</p>
                    {df.to_html(classes='table table-striped table-bordered', index=False)}
                </body>
                </html>
                """
                pdf_buffer = io.BytesIO()
                
                from weasyprint import HTML, CSS # Importación local para claridad
                
                HTML(string=html_reporte).write_pdf(
                    pdf_buffer, 
                    stylesheets=[CSS(filename=css_path)]
                )
                pdf_buffer.seek(0)
                return send_file(
                    pdf_buffer,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'planilla_nomina_{fecha_inicio_str}_a_{fecha_fin_str}.pdf'
                )

            # Fallback en caso de formato no reconocido
            return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina'))


    except Exception as e:
        # Captura errores de fecha, base de datos, o de procesamiento
        logging.exception("Error al generar el reporte de nómina.")
        flash(f'Ocurrió un error técnico al generar el reporte. Por favor, inténtelo de nuevo.', 'danger')
    
    # Redirección final en caso de error o excepción
    return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                            fecha_inicio=fecha_inicio_str,
                            fecha_fin=fecha_fin_str,
                            tipo_nomina_id=id_tipo_nomina_str))

# ====================================================================
# --- REPORTE DE AGUINALDOS ---
# ====================================================================

""" Rutas y lógica para generación de reportes de aguinaldos en varios formatos (HTML, CSV, Excel, PDF)."""
@reportes_bp.route('/reporte_aguinaldos', methods=['GET', 'POST'])
@login_required
@permiso_requerido('rp_aguinaldo')
def mostrar_reporte_aguinaldos():
    """
    Genera y muestra el reporte de aguinaldos con paginación.
    """
    
    # 1. Determinar el año y la página
    ano_str = request.values.get('ano_aguinaldo') or request.values.get('ano', str(datetime.now().year))
    page = request.args.get('page', 1, type=int)
    
    ano_filtrado = None
    paginated_records = None
    tabla_aguinaldos_html = None

    try:
        ano_filtrado = int(ano_str)
        
        # 2. Construir la consulta BASE
        query = db.session.query(Aguinaldo, Empleado).join(Empleado).filter(
            extract('year', Aguinaldo.fecha_pago) == ano_filtrado
        ).order_by(Empleado.apellido_primero, Empleado.nombre)
        
        # 3. Aplicar Paginación
        paginated_records = query.paginate(page=page, per_page=10, error_out=False)
        
        if not paginated_records.items and paginated_records.pages > 0 and page > paginated_records.pages:
            flash("La página solicitada no existe, se muestra la última página.", 'info')
            return redirect(url_for('reportes_bp.mostrar_reporte_aguinaldos', ano_aguinaldo=ano_filtrado, page=paginated_records.pages))
        
        if not paginated_records.items and page == 1:
            flash(f'No se encontraron registros de aguinaldos para el año {ano_filtrado}. (FA1)', 'info')

      # --- Lógica de Formateo y Generación de Tabla (Solo si hay datos) ---
        if paginated_records.items:
            # ... (código para crear data_list) ...
            data_list = []
            for aguinaldo, empleado in paginated_records.items:
                data_list.append({
                    'Cédula': empleado.cedula,
                    'Nombre Empleado': f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}",
                    'Fecha Cálculo': aguinaldo.fecha_pago.strftime('%Y-%m-%d'),
                    'Monto Aguinaldo': aguinaldo.monto
                })
            
            df = pd.DataFrame(data_list)
            
            # Aplicar la función de formato de moneda a la columna 'Monto Aguinaldo'
            for col in ['Monto Aguinaldo']:
                # Esto es correcto: aplica el formato solo a números y deja otros valores (como None) sin tocar
                df[col] = df[col].apply(lambda x: format_currency_es(x) if isinstance(x, (int, float)) else x)

            styles = [
                # Puedes aplicar estilos generales a todas las celdas (td)
                {'selector': 'td', 
                'props': [('text-align', 'left')]} , # Alinea a la derecha todas las celdas (td)
                # Si quieres centrar también el encabezado (th)
                {'selector': 'th', 
                'props': [('text-align', 'center')]}
            ]
            
            # Generar el HTML de la tabla (y asignarlo a la variable ya declarada)
            tabla_aguinaldos_html = (
                df.style
                .set_table_styles(styles) # Aplica los estilos definidos arriba
                .set_table_attributes("class='table table-striped table-hover table-sm'") # Reemplaza el parámetro 'classes'
                .hide(axis="index") # Reemplaza el parámetro 'index=False'
                .to_html()

            )


    except ValueError:
        flash('Por favor, ingrese un año válido.', 'danger')
    except Exception as e:
        flash(f'Error al generar el reporte de aguinaldos: {e} (FA2)', 'danger')
        logging.error(f'Error en reporte_aguinaldos: {e}', exc_info=True)
        
    # 4. Renderizar la plantilla
    return render_template(
        'reporte/rp_aguinaldos.html', 
        paginated_records=paginated_records, 
        ano_filtrado=ano_filtrado,
        current_year=datetime.now().year,
        # Necesitas una lista de años para el filtro de selección
        anos_disponibles=range(datetime.now().year, 2020, -1),
        tabla_aguinaldos_html=tabla_aguinaldos_html
    )
   
""" Función de exportación para aguinaldos en varios formatos (CSV, Excel, PDF). """
@reportes_bp.route('/exportar_aguinaldos/<int:ano>/<string:formato>')
@login_required
@permiso_requerido('rp_aguinaldo')
def exportar_aguinaldos(ano, formato):
    try:
        aguinaldos_data = db.session.query(Aguinaldo, Empleado).join(Empleado).filter(
            extract('year', Aguinaldo.fecha_pago) == ano
        ).all()

        if not aguinaldos_data:
            flash(f'No hay datos para exportar para el año {ano}.', 'info')
            return redirect(url_for('reportes_bp.mostrar_reporte_aguinaldos'))

        # --- Preparar datos en DataFrame para todos los formatos ---
        data_list = []
        for aguinaldo, empleado in aguinaldos_data:
            data_list.append({
                'Año': aguinaldo.fecha_pago.year,
                'Cédula Empleado': empleado.cedula,
                # Asumo que el modelo Empleado tiene apellido_primero y apellido_segundo
                'Nombre Empleado': f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}",
                'Fecha Cálculo': aguinaldo.fecha_pago.strftime('%Y-%m-%d'),
                'Monto Aguinaldo': float(f"{aguinaldo.monto:.2f}")
            })
        df = pd.DataFrame(data_list)
        
        # --- Lógica de exportación según el formato ---
        
        if formato == 'csv':
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_buffer.seek(0)
            return send_file(
                io.BytesIO(csv_buffer.getvalue().encode('utf-8-sig')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'reporte_aguinaldos_{ano}.csv'
            )
        
        elif formato == 'excel':
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False, engine='openpyxl')
            excel_buffer.seek(0)
            return send_file(
                excel_buffer,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'reporte_aguinaldos_{ano}.xlsx'
            )
            
        elif formato == 'pdf':

            for col in ['Monto Aguinaldo']:
                # Aquí se convierte el valor numérico en una CADENA de texto formateada (ej: "₡ 1.234.567,89")
                df[col] = df[col].apply(lambda x: format_currency_es(x) if isinstance(x, (int, float)) else x)

            # Preparar HTML para PDF (similar a como lo haces con Nómina)
            logo_url = url_for('static', filename='img/logo.webp', _external=True)
            css_url = url_for('static', filename='css/reportes.css', _external=True)

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Reporte de Aguinaldos</title>
                <link rel="stylesheet" href="{css_url}"> 
            </head>
            <body>
                <div class="logo-container">
                    <img src="{logo_url}" alt="Logo de la empresa">
                </div>
                <h1>Reporte de Aguinaldos</h1>
                <p><strong>Año:</strong> {ano}</p>
                {df.to_html(classes='table table-striped table-bordered', index=False)}
            </body>
            </html>
            """
            
            pdf_buffer = io.BytesIO()
            # Nota: usamos base_url=request.url_root para que WeasyPrint pueda cargar el CSS y el logo
            HTML(string=html_content, base_url=request.url_root).write_pdf(pdf_buffer)
            pdf_buffer.seek(0)
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'reporte_aguinaldos_{ano}.pdf'
            )
            
        else:
            flash('Formato de exportación no válido.', 'danger')
            return redirect(url_for('reportes_bp.mostrar_reporte_aguinaldos'))

    except Exception as e:
        flash(f'Error al exportar el reporte de aguinaldos: {e} (FA2)', 'danger')
        logging.error(f'Error en exportar_aguinaldos: {e}', exc_info=True)
        return redirect(url_for('reportes_bp.mostrar_reporte_aguinaldos'))

# ====================================================================
# --- REPORTE DE LIQUIDACIONES ---
# ====================================================================

""" Rutas y lógica para generación de reportes de liquidaciones. """

@reportes_bp.route('/reporte_liquidaciones', methods=['GET', 'POST'])
@login_required
@permiso_requerido('rp_liquidacion')
def mostrar_reporte_liquidaciones():
    """
    Genera y muestra el reporte de liquidaciones.
    """
    liquidaciones = []
    fecha_inicio_filtro = None
    fecha_fin_filtro = None
    today = datetime.now().date() # Se añade aquí para que esté disponible en GET

    if request.method == 'POST':
        fecha_inicio_str = request.form.get('fecha_inicio')
        fecha_fin_str = request.form.get('fecha_fin')
        
        try:
            fecha_inicio_filtro = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin_filtro = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

            if fecha_inicio_filtro > fecha_fin_filtro:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'warning')
                return render_template('reporte/rp_liquidaciones.html', liquidaciones=[], today=today)

            # Consulta la base de datos
            liquidaciones = db.session.query(Liquidacion, Empleado).join(Empleado).filter(
                Liquidacion.fecha_pago.between(fecha_inicio_filtro, fecha_fin_filtro)
            ).all()

            if not liquidaciones:
                flash(f'No se encontraron registros de liquidaciones entre {fecha_inicio_str} y {fecha_fin_str}. (FA1)', 'info')

        except (ValueError, TypeError):
            flash('Por favor, ingrese fechas válidas.', 'danger')
        except Exception as e:
            flash(f'Error al generar el reporte de liquidaciones: {e} (FA2)', 'danger')
            # logging.error(f'Error en reporte_liquidaciones: {e}', exc_info=True) # RNF-AR-020, FA2

    return render_template('reporte/rp_liquidaciones.html', 
                            liquidaciones=liquidaciones, 
                            fecha_inicio_filtro=fecha_inicio_filtro,
                            fecha_fin_filtro=fecha_fin_filtro,
                            today=today)

# Función de exportación para liquidaciones en formato CSV (RNF-US-020) - Mantenida para completar el código
@reportes_bp.route('/exportar_liquidaciones/<string:fecha_inicio>/<string:fecha_fin>')
@login_required
@permiso_requerido('rp_liquidacion')
def exportar_liquidaciones_csv(fecha_inicio, fecha_fin):
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d').date()

        liquidaciones = db.session.query(Liquidacion, Empleado).join(Empleado).filter(
            Liquidacion.fecha_pago.between(fecha_inicio_dt, fecha_fin_dt)
        ).all()

        if not liquidaciones:
            flash(f'No hay datos para exportar entre {fecha_inicio} y {fecha_fin}.', 'info')
            return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))

        output = io.StringIO()
        writer = csv.writer(output)

        # Encabezados (RNF-US-020)
        writer.writerow([
            'Cédula Empleado', 'Nombre Empleado', 'Fecha Fin Contrato', 'Fecha Pago', 
            'Monto Total', 'Preaviso', 'Cesantía', 'Vacaciones', 'Aguinaldo', 'Salario Pendiente'
        ])

        for liquidacion, empleado in liquidaciones:
            writer.writerow([
                empleado.cedula,
                f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}",
                liquidacion.fecha_fin_contrato.strftime('%Y-%m-%d'),
                liquidacion.fecha_pago.strftime('%Y-%m-%d'),
                f"{liquidacion.total_monto:.2f}",
                f"{liquidacion.monto_preaviso:.2f}",
                f"{liquidacion.monto_cesantia:.2f}",
                f"{liquidacion.monto_vacaciones:.2f}",
                f"{liquidacion.monto_aguinaldo:.2f}", # 🛑 CORRECCIÓN DE CAMPO
                f"{liquidacion.monto_salario_pendiente:.2f}"
            ])

        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=reporte_liquidaciones_{fecha_inicio}_a_{fecha_fin}.csv"
        response.headers["Content-type"] = "text/csv"
        return response

    except Exception as e:
        flash(f'Error al exportar el reporte de liquidaciones: {e} (FA2)', 'danger')
        # logging.error(f'Error en exportar_liquidaciones_csv: {e}', exc_info=True)
        return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))
    
@reportes_bp.route('/exportar_liquidaciones/<string:fecha_inicio>/<string:fecha_fin>/<string:formato>')
@login_required
@permiso_requerido('rp_liquidacion')
def exportar_liquidaciones(fecha_inicio, fecha_fin, formato):
    try:
        # Nota: Asegúrate de que pandas, weasyprint, send_file y format_currency_es estén disponibles.
        import pandas as pd # Importación requerida para esta función
        # from weasyprint import HTML # Importación requerida para esta función
        # from flask import send_file, url_for # send_file y url_for ya deberían estar importados

        fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d').date()

        liquidaciones_data = db.session.query(Liquidacion, Empleado).join(Empleado).filter(
            Liquidacion.fecha_pago.between(fecha_inicio_dt, fecha_fin_dt)
        ).all()

        if not liquidaciones_data:
            flash(f'No hay datos para exportar entre {fecha_inicio} y {fecha_fin}.', 'info')
            return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))

        # --- Preparar datos en DataFrame para todos los formatos ---
        data_list = []
        for liquidacion, empleado in liquidaciones_data:
            data_list.append({
                'Cédula Empleado': empleado.cedula,
                'Nombre Empleado': f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}",
                'Fecha Fin Contrato': liquidacion.fecha_fin_contrato.strftime('%Y-%m-%d'),
                'Fecha Pago': liquidacion.fecha_pago.strftime('%Y-%m-%d'),
                'Monto Total': float(f"{liquidacion.total_monto:.2f}"),
                'Preaviso': float(f"{liquidacion.monto_preaviso:.2f}"),
                'Cesantía': float(f"{liquidacion.monto_cesantia:.2f}"),
                'Vacaciones': float(f"{liquidacion.monto_vacaciones:.2f}"),
                'Aguinaldo': float(f"{liquidacion.monto_aguinaldo:.2f}"),
                'Salario Pendiente': float(f"{liquidacion.monto_salario_pendiente:.2f}")
            })
        df = pd.DataFrame(data_list)
        
        # --- Lógica de exportación según el formato ---

        if formato == 'csv':
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_buffer.seek(0)
            return send_file(
                io.BytesIO(csv_buffer.getvalue().encode('utf-8-sig')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'reporte_liquidaciones_{fecha_inicio}_a_{fecha_fin}.csv'
            )
        
        elif formato == 'excel':
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False, engine='openpyxl')
            excel_buffer.seek(0)
            return send_file(
                excel_buffer,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'reporte_liquidaciones_{fecha_inicio}_a_{fecha_fin}.xlsx'
            )
            
        elif formato == 'pdf':
            # Columnas monetarias en el DataFrame (DF):
            columnas_a_formatear = [
                'Monto Total', 
                'Preaviso', 
                'Cesantía', 
                'Vacaciones', 
                'Aguinaldo', 
                'Salario Pendiente'
            ]
            
            # Asegurándose de que format_currency_es está disponible y se aplica a todas las columnas:
            for col in columnas_a_formatear:
                try:
                    df[col] = df[col].apply(lambda x: format_currency_es(x) if isinstance(x, (int, float)) else x)
                except NameError:

                    pass 

            # --- Preparar HTML para PDF (Formato completo con logo y CSS) ---
            logo_url = url_for('static', filename='img/logo.webp', _external=True)
            css_url = url_for('static', filename='css/reportes.css', _external=True)

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Reporte de Liquidaciones</title>
                <link rel="stylesheet" href="{css_url}"> 
            </head>
            <body>
                <div class="logo-container">
                    <img src="{logo_url}" alt="Logo de la empresa">
                </div>
                <h1>Reporte de Liquidaciones</h1>
                <p><strong>Período:</strong> {fecha_inicio} a {fecha_fin}</p>
                {df.to_html(classes='table table-striped table-bordered', index=False)}
            </body>
            </html>
            """
            
            # --- Generación y Retorno del PDF ---
            # Requiere WeasyPrint, io y send_file
            pdf_buffer = io.BytesIO()
            HTML(string=html_content, base_url=request.url_root).write_pdf(pdf_buffer)
            pdf_buffer.seek(0)
            
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'reporte_liquidaciones_{fecha_inicio}_a_{fecha_fin}.pdf'
            )
        
        else:
            flash('Formato de exportación no válido.', 'danger')
            return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))

    except Exception as e:
        # Aquí manejamos cualquier error, incluyendo la falla de WeasyPrint (si no está instalado).
        flash(f'Error al exportar el reporte de liquidaciones. Asegúrese de que WeasyPrint y sus dependencias (cairo/pango) estén instalados: {e} (FA2)', 'danger')
        # logging.error(f'Error en exportar_liquidaciones: {e}', exc_info=True)
        return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))
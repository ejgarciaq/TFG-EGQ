import csv
from flask import Blueprint, current_app, make_response, request, render_template, flash, redirect, url_for, send_file
from flask_login import login_required
from sqlalchemy import extract
from payroll_app.models import Aguinaldo, Liquidacion, db, Empleado, RegistroAsistencia, Nomina, TipoNomina
from weasyprint import HTML, CSS
from datetime import datetime
import pandas as pd
import io,logging
from sqlalchemy.orm import joinedload, aliased

from payroll_app.routes.decorators import permiso_requerido
# from flask_login import login_required


reportes_bp = Blueprint('reportes_bp', __name__)


@reportes_bp.route('/asistencia', methods=['GET'])
@login_required # Proteger esta ruta con login y roles si es necesario
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

@reportes_bp.route('/asistencia/reporte', methods=['GET', 'POST'])
@login_required # Proteger esta ruta con login y roles si es necesario
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
                    <link rel="stylesheet" href="{url_for('static', filename='css/reportes.css')}">
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


# --- NUEVA FUNCIÓN: Generar y descargar el reporte de NÓMINA ---

@reportes_bp.route('/nomina', methods=['GET'])
@login_required # Proteger esta ruta con login y roles si es necesario
def mostrar_pagina_reporte_nomina():
    """Renderiza la página del formulario para generar reportes de nómina."""
    tipos_nomina = TipoNomina.query.all()
    fecha_inicio_seleccionada = request.args.get('fecha_inicio', '')
    fecha_fin_seleccionada = request.args.get('fecha_fin', '')
    id_tipo_nomina_seleccionado = request.args.get('tipo_nomina_id', 'todos')

    return render_template(
        'rp_nomina.html',
        tipos_nomina=tipos_nomina,
        fecha_inicio_seleccionada=fecha_inicio_seleccionada,
        fecha_fin_seleccionada=fecha_fin_seleccionada,
        id_tipo_nomina_seleccionado=id_tipo_nomina_seleccionado,
    )


@reportes_bp.route('/nomina/generar', methods=['GET'])
@login_required # Proteger esta ruta con login y roles si es necesario
def generar_reporte_nomina():
    """Genera y descarga el reporte de nómina en el formato solicitado."""
    
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    id_tipo_nomina_str = request.args.get('tipo_nomina_id', '')
    descargar_formato = request.args.get('descargar', 'html')

    if not fecha_inicio_str or not fecha_fin_str:
        flash('Por favor, selecciona un rango de fechas para generar el reporte de nómina.', 'warning')
        return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina'))

    try:
        fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        id_tipo_nomina_int = int(id_tipo_nomina_str) if id_tipo_nomina_str and id_tipo_nomina_str != 'todos' else None

        if fecha_inicio_obj > fecha_fin_obj:
            flash('La fecha de inicio no puede ser posterior a la fecha de fin para el reporte.', 'warning')
            return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                                     fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str,
                                     tipo_nomina_id=id_tipo_nomina_str))

        # --- Consulta de las nóminas ya calculadas y almacenadas ---
        
        # PASO 1: Crea un alias para el modelo Empleado
        EmpleadoAlias = aliased(Empleado)

        query_nominas = Nomina.query.options(
            # Usa el alias en joinedload para asegurar que SQLAlchemy usa el alias correcto para la carga
            joinedload(Nomina.empleado.of_type(EmpleadoAlias)), 
            joinedload(Nomina.tipo_nomina_relacion)
        ).filter(
            Nomina.fecha_inicio >= fecha_inicio_obj,
            Nomina.fecha_fin <= fecha_fin_obj
        )
        
        # PASO 2: Usa el alias en la cláusula order_by
        query_nominas = query_nominas.order_by(
            Nomina.fecha_creacion.desc(), 
            EmpleadoAlias.nombre.asc(), 
            EmpleadoAlias.apellido_primero.asc(), 
            EmpleadoAlias.apellido_segundo.asc()
        )

        if id_tipo_nomina_int:
            query_nominas = query_nominas.filter(Nomina.TipoNomina_id_tipo_nomina == id_tipo_nomina_int)
        
        nominas_reporte = query_nominas.all()

        if not nominas_reporte:
            flash('No se encontraron nóminas generadas para los criterios seleccionados para el reporte.', 'info')
            return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                                     fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str,
                                     tipo_nomina_id=id_tipo_nomina_str))

        # --- Preparar los datos para Pandas DataFrame ---
        data_for_df = [{
            "Nombre Completo": n.empleado.nombre_completo if n.empleado else 'N/A', 
            "Cédula": n.empleado.cedula if n.empleado else 'N/A',
            "Tipo de Nómina": n.tipo_nomina_relacion.nombre_tipo if n.tipo_nomina_relacion else 'N/A',
            "Período de Nómina": f"{n.fecha_inicio.strftime('%Y-%m-%d')} a {n.fecha_fin.strftime('%Y-%m-%d')}",
            "Salario Bruto": f"{n.salario_bruto:,.2f}",
            "Deducciones Totales": f"{n.deducciones:,.2f}",
            "Salario Neto": f"{n.salario_neto:,.2f}",
            "Fecha de Generación": n.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S')
        } for n in nominas_reporte]
        
        df = pd.DataFrame(data_for_df)

        def format_currency_es(value):
            if isinstance(value, (int, float)):
                # Formatea a 2 decimales, luego reemplaza el separador de miles (coma por punto)
                # y el separador decimal (punto por coma)
                return f"{value:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
            return value # Retorna el valor tal cual si no es numérico

        # --- Lógica de descarga según el formato solicitado (sin cambios) ---
        if descargar_formato == 'csv':
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_buffer.seek(0)
            return send_file(
                io.BytesIO(csv_buffer.getvalue().encode('utf-8-sig')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'reporte_nomina_{fecha_inicio_str}_a_{fecha_fin_str}.csv'
            )
        
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

        elif descargar_formato == 'pdf':
            tipos_nomina_disponibles = TipoNomina.query.all()
            tipo_nomina_nombre = next(
                (t.nombre_tipo for t in tipos_nomina_disponibles if str(t.id_tipo_nomina) == id_tipo_nomina_str),
                'Todos'
            )
            
            logo_url = url_for('static', filename='img/logo.webp', _external=True)

            css_url = url_for('static', filename='css/reportes.css', _external=True)


            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Reporte de Nómina</title>
                <link rel="stylesheet" href="{css_url}"> 
                <style>
                    /* Puedes dejar estilos específicos de impresión aquí, como @page */
                    @page {{ size: A4 landscape; }} 
                </style>
            </head>
            <body>
                <div class="logo-container">
                    <img src="{logo_url}" alt="Logo de la empresa">
                </div>
                <h1>Nómina</h1>
                <p><strong>Período:</strong> {fecha_inicio_str} a {fecha_fin_str}</p>
                <p><strong>Tipo de Nómina:</strong> {tipo_nomina_nombre}</p>
                {df.to_html(classes='table table-striped table-bordered', index=False)}
            </body>
            </html>
            """
            
            pdf_buffer = io.BytesIO()
            HTML(string=html_content, base_url=request.url_root).write_pdf(pdf_buffer)
            pdf_buffer.seek(0)
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'planilla_nomina_{fecha_inicio_str}_a_{fecha_fin_str}.pdf'
            )

    except ValueError:
        flash('Formato de fecha inválido para el reporte. Por favor, seleccione fechas del calendario.', 'danger')
        logging.exception("Error de formato de fecha en generar_reporte_nomina.")
    except Exception as e:
        flash(f'Ocurrió un error al generar el reporte de nómina. Detalle: {str(e)}', 'danger')
        logging.exception("Error al generar el reporte de nómina.")
    
    return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                            fecha_inicio=fecha_inicio_str,
                            fecha_fin=fecha_fin_str,
                            tipo_nomina_id=id_tipo_nomina_str))



# ====================================================================
# --- REPORTE DE AGUINALDOS ---
# ====================================================================

@reportes_bp.route('/reporte_aguinaldos', methods=['GET', 'POST'])
@login_required
#@permiso_requerido('administrador') # RNF-SE-020
def mostrar_reporte_aguinaldos():
    """
    Genera y muestra el reporte de aguinaldos. (Pasos 3 a 7)
    """
    aguinaldos = []
    ano_filtrado = None
    
    if request.method == 'POST':
        ano_str = request.form.get('ano_aguinaldo')
        try:
            ano_filtrado = int(ano_str)
            # Consulta la base de datos para obtener los aguinaldos de ese año (Paso 6)
            aguinaldos = db.session.query(Aguinaldo, Empleado).join(Empleado).filter(
                db.extract('year', Aguinaldo.fecha_pago) == ano_filtrado # Uso correcto de db.extract
            ).all()

            if not aguinaldos:
                flash(f'No se encontraron registros de aguinaldos para el año {ano_filtrado}. (FA1)', 'info')
            
        except ValueError:
            flash('Por favor, ingrese un año válido.', 'danger')
        except Exception as e:
            flash(f'Error al generar el reporte de aguinaldos: {e} (FA2)', 'danger')
            logging.error(f'Error en reporte_aguinaldos: {e}', exc_info=True) # RNF-AR-020, FA2
            
    return render_template('rp_aguinaldos.html', 
                           aguinaldos=aguinaldos, 
                           ano_filtrado=ano_filtrado,
                           current_year=datetime.now().year)

# Función de exportación para aguinaldos (Paso 8)
@reportes_bp.route('/exportar_aguinaldos/<int:ano>')
#@login_required
#@permiso_requerido('administrador')
def exportar_aguinaldos_csv(ano):
    try:
        aguinaldos = db.session.query(Aguinaldo, Empleado).join(Empleado).filter(
            extract('year', Aguinaldo.fecha_pago) == ano
        ).all()

        if not aguinaldos:
            flash(f'No hay datos para exportar para el año {ano}.', 'info')
            return redirect(url_for('reportes_bp.mostrar_reporte_aguinaldos'))

        output = io.StringIO()
        writer = csv.writer(output)

        # Encabezados (RNF-US-020)
        writer.writerow(['Año', 'Cédula Empleado', 'Nombre Empleado', 'Fecha Cálculo', 'Monto Aguinaldo'])

        for aguinaldo, empleado in aguinaldos:
            writer.writerow([
                aguinaldo.fecha_pago.year,
                empleado.cedula,
                f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}",
                aguinaldo.fecha_pago.strftime('%Y-%m-%d'),
                f"{aguinaldo.monto:.2f}"
            ])

        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=reporte_aguinaldos_{ano}.csv"
        response.headers["Content-type"] = "text/csv"
        return response

    except Exception as e:
        flash(f'Error al exportar el reporte de aguinaldos: {e} (FA2)', 'danger')
        logging.error(f'Error en exportar_aguinaldos_csv: {e}', exc_info=True)
        return redirect(url_for('reportes_bp.mostrar_reporte_aguinaldos'))
    
# Función de exportación para aguinaldos (Paso 8)
@reportes_bp.route('/exportar_aguinaldos/<int:ano>/<string:formato>')
@login_required
#@permiso_requerido('administrador')
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
                <style>
                    @page {{ size: A4 landscape; }} 
                </style>
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

@reportes_bp.route('/reporte_liquidaciones', methods=['GET', 'POST'])
@login_required
#@permiso_requerido('administrador') # RNF-SE-020
def mostrar_reporte_liquidaciones():
    """
    Genera y muestra el reporte de liquidaciones. (Pasos 3 a 7)
    """
    liquidaciones = []
    fecha_inicio_filtro = None
    fecha_fin_filtro = None

    if request.method == 'POST':
        fecha_inicio_str = request.form.get('fecha_inicio')
        fecha_fin_str = request.form.get('fecha_fin')
        
        try:
            fecha_inicio_filtro = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin_filtro = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

            if fecha_inicio_filtro > fecha_fin_filtro:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'warning')
                return render_template('rp_liquidaciones.html', liquidaciones=[], today=datetime.now().date())

            # Consulta la base de datos (Paso 6)
            liquidaciones = db.session.query(Liquidacion, Empleado).join(Empleado).filter(
                Liquidacion.fecha_pago.between(fecha_inicio_filtro, fecha_fin_filtro)
            ).all()

            if not liquidaciones:
                flash(f'No se encontraron registros de liquidaciones entre {fecha_inicio_str} y {fecha_fin_str}. (FA1)', 'info')

        except (ValueError, TypeError):
            flash('Por favor, ingrese fechas válidas.', 'danger')
        except Exception as e:
            flash(f'Error al generar el reporte de liquidaciones: {e} (FA2)', 'danger')
            logging.error(f'Error en reporte_liquidaciones: {e}', exc_info=True) # RNF-AR-020, FA2

    return render_template('rp_liquidaciones.html', 
                           liquidaciones=liquidaciones, 
                           fecha_inicio_filtro=fecha_inicio_filtro,
                           fecha_fin_filtro=fecha_fin_filtro,
                           today=datetime.now().date())

# Función de exportación para liquidaciones (Paso 8)
@reportes_bp.route('/exportar_liquidaciones/<string:fecha_inicio>/<string:fecha_fin>')
@login_required
#@permiso_requerido('administrador')
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
                f"{liquidacion.monto:.2f}",
                f"{liquidacion.monto_salario_pendiente:.2f}"
            ])

        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=reporte_liquidaciones_{fecha_inicio}_a_{fecha_fin}.csv"
        response.headers["Content-type"] = "text/csv"
        return response

    except Exception as e:
        flash(f'Error al exportar el reporte de liquidaciones: {e} (FA2)', 'danger')
        logging.error(f'Error en exportar_liquidaciones_csv: {e}', exc_info=True)
        return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))
    
    # Función de exportación para liquidaciones (Paso 8)
@reportes_bp.route('/exportar_liquidaciones/<string:fecha_inicio>/<string:fecha_fin>/<string:formato>')
@login_required
#@permiso_requerido('administrador')
def exportar_liquidaciones(fecha_inicio, fecha_fin, formato):
    try:
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
                'Aguinaldo': float(f"{liquidacion.monto:.2f}"),
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
            # Preparar HTML para PDF
            logo_url = url_for('static', filename='img/logo.webp', _external=True)
            css_url = url_for('static', filename='css/reportes.css', _external=True)

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Reporte de Liquidaciones</title>
                <link rel="stylesheet" href="{css_url}"> 
                <style>
                    @page {{ size: A4 landscape; }} 
                </style>
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
        flash(f'Error al exportar el reporte de liquidaciones: {e} (FA2)', 'danger')
        logging.error(f'Error en exportar_liquidaciones: {e}', exc_info=True)
        return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))
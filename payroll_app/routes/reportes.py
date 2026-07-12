import csv
import io
import logging
import os
from flask import ( Blueprint, current_app, make_response, request, render_template, flash, redirect, url_for, send_file )
from flask_login import login_required
from sqlalchemy import extract
from payroll_app.models import Aguinaldo, Liquidacion, db, Empleado, RegistroAsistencia, Nomina, TipoNomina
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import joinedload, aliased
from payroll_app.routes.decorators import permiso_requerido
from payroll_app.pdf_utils import build_pdf_from_rows

""" Rutas y lógica para generación de reportes en varios formatos (HTML, CSV, Excel, PDF)."""
reportes_bp = Blueprint('reportes_bp', __name__)


""" FUNCIÓN AUXILIAR PARA LA GENERACIÓN DE ARCHIVOS EN SEGUNDO PLANO """
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
            pdf_bytes = build_pdf_from_rows(
                title='Reporte temporal',
                rows=[('Archivo', filename)],
                metadata={'Formato': format},
            )
            with open(filepath, 'wb') as handle:
                handle.write(pdf_bytes)
            
        logging.info(f"Archivo '{filename}' generado con éxito en: {filepath}")

    except Exception as e:
        logging.exception(f"Error en el hilo al generar el archivo {filename}: {e}")


""" Función auxiliar para formatear moneda en español de Costa Rica."""
def format_currency_es(value):
    """Formatea un valor numérico a formato de moneda (separador de miles: '.', decimal: ',')."""
    if value is None:
        return '₡ 0,00'
        
    if isinstance(value, (int, float)):
        formatted = f"{abs(value):,.2f}"
        formatted = formatted.replace(",", "#")
        formatted = formatted.replace(".", ",")
        formatted = formatted.replace("#", ".")
        signo = '-' if value < 0 else ''
        return f"{signo}₡ {formatted}"
    
    return str(value)


# ====================================================================
# --- REPORTE DE ASISTENCIA ---
# ====================================================================

@reportes_bp.route('/asistencia', methods=['GET'])
@permiso_requerido('rp_asistencia')
@login_required
def mostrar_pagina_reporte():
    empleados = Empleado.query.all()
    return render_template( 
        'reporte/rp_asistencia.html',
        empleados=empleados,
        empleado_id_seleccionado='todos',
        fecha_inicio_seleccionada='',
        fecha_fin_seleccionada='' )


@reportes_bp.route('/asistencia', methods=['GET', 'POST'])
@permiso_requerido('rp_asistencia')
@login_required
def generar_reporte():
    empleados = Empleado.query.all()
    reporte_html = None
    
    empleado_id_seleccionado = request.form.get('empleado_id', request.args.get('empleado_id', 'todos'))
    fecha_inicio_str = request.form.get('fecha_inicio', request.args.get('fecha_inicio', ''))
    fecha_fin_str = request.form.get('fecha_fin', request.args.get('fecha_fin', ''))
    descargar_formato = request.form.get('descargar', request.args.get('descargar', 'html')) 
    
    is_download_request = descargar_formato in ['csv', 'excel', 'pdf']
    
    if fecha_inicio_str and fecha_fin_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

            if fecha_inicio > fecha_fin:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'warning')
            else:
                base_query = db.session.query(RegistroAsistencia).join(Empleado).filter(
                    RegistroAsistencia.fecha_registro.between(fecha_inicio, fecha_fin)
                ).order_by(RegistroAsistencia.fecha_registro.asc(), Empleado.nombre.asc())
                
                if empleado_id_seleccionado != 'todos':
                    base_query = base_query.filter(RegistroAsistencia.Empleado_id_empleado == int(empleado_id_seleccionado))

                registros = base_query.all()
                
                if registros:
                    # Extracción blindada contra valores nulos o None en la BD
                    data = [{
                        'Empleado': registro.empleado.nombre_completo if (registro.empleado and getattr(registro.empleado, 'nombre_completo', None)) else 'N/A',
                        'Fecha': registro.fecha_registro.strftime('%Y-%m-%d') if registro.fecha_registro else 'N/A',
                        'Hora Entrada': registro.hora_entrada.strftime('%I:%M:%S %p') if getattr(registro, 'hora_entrada', None) else 'N/A',
                        'Salida Almuerzo': registro.hora_salida_almuerzo.strftime('%I:%M:%S %p') if getattr(registro, 'hora_salida_almuerzo', None) else 'N/A',
                        'Regreso Almuerzo': registro.hora_entrada_almuerzo.strftime('%I:%M:%S %p') if getattr(registro, 'hora_entrada_almuerzo', None) else 'N/A',
                        'Hora Salida': registro.hora_salida.strftime('%I:%M:%S %p') if getattr(registro, 'hora_salida', None) else 'N/A',
                        'Total Horas': f"{registro.total_horas:.2f}" if isinstance(registro.total_horas, (int, float)) else '0.00',
                        'Horas Extra': f"{registro.hora_extra:.2f}" if isinstance(registro.hora_extra, (int, float)) else '0.00',
                        'Horas Feriado': f"{registro.hora_feriado:.2f}" if isinstance(registro.hora_feriado, (int, float)) else '0.00',
                        'Aprobado': 'Sí' if registro.aprobacion_registro else 'No',
                    } for registro in registros]
                    
                    df_download = pd.DataFrame(data)
                    
                    if not is_download_request:
                        reporte_html = df_download.to_html(classes='table table-striped table-bordered table-hover mt-3', index=False)
                    
                    if descargar_formato == 'csv':
                        csv_buffer = io.StringIO()
                        df_download.to_csv(csv_buffer, index=False)
                        csv_buffer.seek(0)
                        return send_file(io.BytesIO(csv_buffer.getvalue().encode('utf-8')), 
                                         mimetype='text/csv', 
                                         as_attachment=True, 
                                         download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.csv')
                    
                    elif descargar_formato == 'excel':
                        excel_buffer = io.BytesIO()
                        df_download.to_excel(excel_buffer, index=False, engine='openpyxl')
                        excel_buffer.seek(0)
                        return send_file(excel_buffer, 
                                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                                         as_attachment=True, 
                                         download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.xlsx')

                    elif descargar_formato == 'pdf':
                        empleado_obj = Empleado.query.get(int(empleado_id_seleccionado)) if empleado_id_seleccionado.isdigit() else None
                        empleado_info = empleado_obj.nombre_completo if empleado_obj else 'Todos'
                        
                        rows = []
                        for index, row in df_download.iterrows():
                            rows.append([
                                str(row['Empleado']),
                                str(row['Fecha']),
                                str(row['Hora Entrada']),
                                str(row['Salida Almuerzo']),
                                str(row['Regreso Almuerzo']),
                                str(row['Hora Salida'])
                            ])
                        
                        pdf_bytes = build_pdf_from_rows(
                            title='Reporte de Asistencia',
                            rows=rows,
                            metadata={'Empleado': empleado_info, 'Desde': fecha_inicio_str, 'Hasta': fecha_fin_str},
                            headers=["Empleado", "Fecha", "Hora Entrada", "Salida Almuerzo", "Regreso Almuerzo", "Hora Salida"]
                        )
                        pdf_buffer = io.BytesIO(pdf_bytes)
                        pdf_buffer.seek(0)
                        return send_file(
                            pdf_buffer,
                            mimetype='application/pdf',
                            as_attachment=True,
                            download_name=f'reporte_asistencia_{fecha_inicio_str}_a_{fecha_fin_str}.pdf'
                        )
                else:
                    flash('No se encontraron registros de asistencia para los criterios de búsqueda.', 'info')
                    reporte_html = None 

        except Exception as e:
            logging.exception("Error controlado al generar el reporte de asistencia.")
            flash('Ocurrió un error técnico al generar el reporte. Por favor, inténtelo de nuevo.', 'danger')
            
    return render_template(
        'reporte/rp_asistencia.html',
        empleados=empleados,
        empleado_id_seleccionado=empleado_id_seleccionado,
        fecha_inicio_seleccionada=fecha_inicio_str,
        fecha_fin_seleccionada=fecha_fin_str,
        reporte_html=reporte_html,
    )


# ====================================================================
# --- REPORTE DE NÓMINA ---
# ====================================================================

@reportes_bp.route('/nomina', methods=['GET'])
@permiso_requerido('rp_nomina')
@login_required
def mostrar_pagina_reporte_nomina():
    tipos_nomina = TipoNomina.query.all()
    fecha_inicio_seleccionada = request.args.get('fecha_inicio', '')
    fecha_fin_seleccionada = request.args.get('fecha_fin', '')
    id_tipo_nomina_seleccionado = request.args.get('tipo_nomina_id', 'todos')
    
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


@reportes_bp.route('/nomina/generar', methods=['GET']) 
@permiso_requerido('rp_nomina')
@login_required
def generar_reporte_nomina():
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    id_tipo_nomina_str = request.args.get('tipo_nomina_id', 'todos')
    descargar_formato = request.args.get('descargar', 'html')
    page = request.args.get('page', 1, type=int)

    if not fecha_inicio_str or not fecha_fin_str:
        flash('Por favor, selecciona un rango de fechas para generar el reporte de nómina.', 'warning')
        return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina')) 

    try:
        fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        id_tipo_nomina_int = int(id_tipo_nomina_str) if id_tipo_nomina_str != 'todos' else None

        if fecha_inicio_obj > fecha_fin_obj:
            flash('La fecha de inicio no puede ser posterior a la fecha de fin para el reporte.', 'warning')
            return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                                     fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str,
                                     tipo_nomina_id=id_tipo_nomina_str))

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
        
        if descargar_formato == 'html':
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
                return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                                         fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str,
                                         tipo_nomina_id=id_tipo_nomina_str))

            data_for_df = [{
                 "Nombre Completo": n.empleado.nombre_completo if (n.empleado and getattr(n.empleado, 'nombre_completo', None)) else 'N/A', 
                 "Cédula": n.empleado.cedula if n.empleado else 'N/A',
                 "Tipo de Nómina": n.tipo_nomina_relacion.nombre_tipo if n.tipo_nomina_relacion else 'N/A',
                 "Período de Nómina": f"{n.fecha_inicio.strftime('%Y-%m-%d') if n.fecha_inicio else 'N/A'} a {n.fecha_fin.strftime('%Y-%m-%d') if n.fecha_fin else 'N/A'}",
                 "Salario Bruto": n.salario_bruto if n.salario_bruto is not None else 0.0,
                 "Deducciones Totales": n.deducciones if n.deducciones is not None else 0.0,
                 "Salario Neto": n.salario_neto if n.salario_neto is not None else 0.0,
                 "Fecha de Generación": n.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S') if n.fecha_creacion else 'N/A'
            } for n in nominas_reporte]
            
            df = pd.DataFrame(data_for_df)
            
            for col in ["Salario Bruto", "Deducciones Totales", "Salario Neto"]:
                 df[col] = df[col].apply(lambda x: format_currency_es(x) if isinstance(x, (int, float)) else x)

            tabla_html = df.to_html(classes='table table-striped table-bordered table-hover mt-3', index=False, border=0)

            return render_template(
                'reporte/rp_nomina.html',
                tipos_nomina=tipos_nomina,
                fecha_inicio_seleccionada=fecha_inicio_str,
                fecha_fin_seleccionada=fecha_fin_str,
                id_tipo_nomina_seleccionado=id_tipo_nomina_str,
                tabla_nomina_html=tabla_html,
                paginated_records=paginated_records,
                tipo_nomina_nombre=tipo_nomina_nombre
            )

        else:
            nominas_reporte_completo = query_nominas.all()
            
            if not nominas_reporte_completo:
                 flash(f'No se encontraron nóminas para descargar en formato {descargar_formato}.', 'info')
                 return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                                          fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str,
                                          tipo_nomina_id=id_tipo_nomina_str))

            data_for_df_completo = [{
                "Nombre Completo": n.empleado.nombre_completo if (n.empleado and getattr(n.empleado, 'nombre_completo', None)) else 'N/A', 
                "Cédula": n.empleado.cedula if n.empleado else 'N/A',
                "Tipo de Nómina": n.tipo_nomina_relacion.nombre_tipo if n.tipo_nomina_relacion else 'N/A',
                "Período de Nómina": f"{n.fecha_inicio.strftime('%Y-%m-%d') if n.fecha_inicio else 'N/A'} a {n.fecha_fin.strftime('%Y-%m-%d') if n.fecha_fin else 'N/A'}",
                "Salario Bruto": n.salario_bruto if n.salario_bruto is not None else 0.0,
                "Deducciones Totales": n.deducciones if n.deducciones is not None else 0.0,
                "Salario Neto": n.salario_neto if n.salario_neto is not None else 0.0,
                "Fecha de Generación": n.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S') if n.fecha_creacion else 'N/A'
            } for n in nominas_reporte_completo]
            df = pd.DataFrame(data_for_df_completo)
            
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
                tipo_nomina_nombre_descarga = next(
                    (t.nombre_tipo for t in TipoNomina.query.all() if str(t.id_tipo_nomina) == id_tipo_nomina_str),
                    'Todos'
                )
                
                for col in ["Salario Bruto", "Deducciones Totales", "Salario Neto"]:
                    df[col] = df[col].apply(format_currency_es)

                rows = []
                for index, r in df.iterrows():
                    rows.append([
                        str(r['Nombre Completo']),
                        str(r['Período de Nómina']),
                        str(r['Cédula']),
                        str(r['Salario Bruto']),
                        str(r['Deducciones Totales']),
                        str(r['Salario Neto'])
                    ])

                pdf_bytes = build_pdf_from_rows(
                    title='Reporte de Nómina Salarial',
                    rows=rows,
                    metadata={'Período': f'{fecha_inicio_str} a {fecha_fin_str}', 'Tipo de Nómina': tipo_nomina_nombre_descarga},
                    headers=["Empleado", "Período", "Cédula", "Salario Bruto", "Deducciones", "Salario Neto"]
                )
                pdf_buffer = io.BytesIO(pdf_bytes)
                pdf_buffer.seek(0)
                return send_file(
                    pdf_buffer,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'planilla_nomina_{fecha_inicio_str}_a_{fecha_fin_str}.pdf'
                )

            return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina'))

    except Exception as e:
        logging.exception("Error al generar el reporte de nómina.")
        flash(f'Ocurrió un error técnico al generar el reporte. Por favor, inténtelo de nuevo.', 'danger')
    
    return redirect(url_for('reportes_bp.mostrar_pagina_reporte_nomina',
                            fecha_inicio=fecha_inicio_str,
                            fecha_fin=fecha_fin_str,
                            tipo_nomina_id=id_tipo_nomina_str))


# ====================================================================
# --- REPORTE DE AGUINALDOS ---
# ====================================================================

@reportes_bp.route('/reporte_aguinaldos', methods=['GET', 'POST'])
@login_required
@permiso_requerido('rp_aguinaldo')
def mostrar_reporte_aguinaldos():
    ano_str = request.values.get('ano_aguinaldo') or request.values.get('ano', str(datetime.now().year))
    page = request.args.get('page', 1, type=int)
    
    ano_filtrado = None
    paginated_records = None
    tabla_aguinaldos_html = None

    try:
        ano_filtrado = int(ano_str)
        
        query = db.session.query(Aguinaldo, Empleado).join(Empleado).filter(
            extract('year', Aguinaldo.fecha_pago) == ano_filtrado
        ).order_by(Empleado.apellido_primero, Empleado.nombre)
        
        paginated_records = query.paginate(page=page, per_page=10, error_out=False)
        
        if not paginated_records.items and paginated_records.pages > 0 and page > paginated_records.pages:
            flash("La página solicitada no existe, se muestra la última página.", 'info')
            return redirect(url_for('reportes_bp.mostrar_reporte_aguinaldos', ano_aguinaldo=ano_filtrado, page=paginated_records.pages))
        
        if not paginated_records.items and page == 1:
            flash(f'No se encontraron registros de aguinaldos para el año {ano_filtrado}. (FA1)', 'info')

        if paginated_records.items:
            data_list = []
            for aguinaldo, empleado in paginated_records.items:
                data_list.append({
                    'Cédula': empleado.cedula if empleado else 'N/A',
                    'Nombre Empleado': f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}" if empleado else 'N/A',
                    'Fecha Cálculo': aguinaldo.fecha_pago.strftime('%Y-%m-%d') if aguinaldo.fecha_pago else 'N/A',
                    'Monto Aguinaldo': aguinaldo.monto if aguinaldo.monto is not None else 0.0
                })
            
            df = pd.DataFrame(data_list)
            
            for col in ['Monto Aguinaldo']:
                df[col] = df[col].apply(lambda x: format_currency_es(x) if isinstance(x, (int, float)) else x)

            styles = [
                {'selector': 'td', 'props': [('text-align', 'left')]},
                {'selector': 'th', 'props': [('text-align', 'center')]}
            ]
            
            tabla_aguinaldos_html = (
                df.style
                .set_table_styles(styles)
                .set_table_attributes("class='table table-striped table-hover table-sm'")
                .hide(axis="index")
                .to_html()
            )

    except ValueError:
        flash('Por favor, ingrese un año válido.', 'danger')
    except Exception as e:
        flash(f'Error al generar el reporte de aguinaldos: {e} (FA2)', 'danger')
        logging.error(f'Error en reporte_aguinaldos: {e}', exc_info=True)
        
    return render_template(
        'reporte/rp_aguinaldos.html', 
        paginated_records=paginated_records, 
        ano_filtrado=ano_filtrado,
        current_year=datetime.now().year,
        anos_disponibles=range(datetime.now().year, 2020, -1),
        tabla_aguinaldos_html=tabla_aguinaldos_html
    )
   

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

        data_list = []
        for aguinaldo, empleado in aguinaldos_data:
            data_list.append({
                'Año': aguinaldo.fecha_pago.year if aguinaldo.fecha_pago else ano,
                'Cédula Empleado': empleado.cedula if empleado else 'N/A',
                'Nombre Empleado': f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}" if empleado else 'N/A',
                'Fecha Cálculo': aguinaldo.fecha_pago.strftime('%Y-%m-%d') if aguinaldo.fecha_pago else 'N/A',
                'Monto Aguinaldo': float(f"{aguinaldo.monto:.2f}") if aguinaldo.monto is not None else 0.0
            })
        df = pd.DataFrame(data_list)
        
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
                df[col] = df[col].apply(lambda x: format_currency_es(x) if isinstance(x, (int, float)) else x)

            rows = []
            for index, r in df.iterrows():
                rows.append([
                    str(r['Nombre Empleado']),
                    str(r['Fecha Cálculo']),
                    str(r['Cédula Empleado']),
                    str(r['Año']),
                    str(r['Monto Aguinaldo'])
                ])

            pdf_bytes = build_pdf_from_rows(
                title='Reporte de Aguinaldos',
                rows=rows,
                metadata={'Año': str(ano)},
                headers=["Empleado", "Fecha Cálculo", "Cédula", "Año", "Monto Aguinaldo"]
            )
            pdf_buffer = io.BytesIO(pdf_bytes)
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
@permiso_requerido('rp_liquidacion')
def mostrar_reporte_liquidaciones():
    liquidaciones = []
    fecha_inicio_filtro = None
    fecha_fin_filtro = None
    today = datetime.now().date()

    if request.method == 'POST':
        fecha_inicio_str = request.form.get('fecha_inicio')
        fecha_fin_str = request.form.get('fecha_fin')
        
        try:
            fecha_inicio_filtro = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin_filtro = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

            if fecha_inicio_filtro > fecha_fin_filtro:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'warning')
                return render_template('reporte/rp_liquidaciones.html', liquidaciones=[], today=today)

            liquidaciones = db.session.query(Liquidacion, Empleado).join(Empleado).filter(
                Liquidacion.fecha_pago.between(fecha_inicio_filtro, fecha_fin_filtro)
            ).all()

            if not liquidaciones:
                flash(f'No se encontraron registros de liquidaciones entre {fecha_inicio_str} y {fecha_fin_str}. (FA1)', 'info')

        except (ValueError, TypeError):
            flash('Por favor, ingrese fechas válidas.', 'danger')
        except Exception as e:
            flash(f'Error al generar el reporte de liquidaciones: {e} (FA2)', 'danger')

    return render_template('reporte/rp_liquidaciones.html', 
                            liquidaciones=liquidaciones, 
                            fecha_inicio_filtro=fecha_inicio_filtro,
                            fecha_fin_filtro=fecha_fin_filtro,
                            today=today)


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

        writer.writerow([
            'Cédula Empleado', 'Nombre Empleado', 'Fecha Fin Contrato', 'Fecha Pago', 
            'Monto Total', 'Preaviso', 'Cesantía', 'Vacaciones', 'Aguinaldo', 'Salario Pendiente'
        ])

        for liquidacion, empleado in liquidaciones:
            writer.writerow([
                empleado.cedula if empleado else 'N/A',
                f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}" if empleado else 'N/A',
                liquidacion.fecha_fin_contrato.strftime('%Y-%m-%d') if liquidacion.fecha_fin_contrato else 'N/A',
                liquidacion.fecha_pago.strftime('%Y-%m-%d') if liquidacion.fecha_pago else 'N/A',
                f"{liquidacion.total_monto:.2f}" if liquidacion.total_monto is not None else '0.00',
                f"{liquidacion.monto_preaviso:.2f}" if liquidacion.monto_preaviso is not None else '0.00',
                f"{liquidacion.monto_cesantia:.2f}" if liquidacion.monto_cesantia is not None else '0.00',
                f"{liquidacion.monto_vacaciones:.2f}" if liquidacion.monto_vacaciones is not None else '0.00',
                f"{liquidacion.monto_aguinaldo:.2f}" if liquidacion.monto_aguinaldo is not None else '0.00',
                f"{liquidacion.monto_salario_pendiente:.2f}" if liquidacion.monto_salario_pendiente is not None else '0.00'
            ])

        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=reporte_liquidaciones_{fecha_inicio}_a_{fecha_fin}.csv"
        response.headers["Content-type"] = "text/csv"
        return response

    except Exception as e:
        flash(f'Error al exportar el reporte de liquidaciones: {e} (FA2)', 'danger')
        return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))
    


@reportes_bp.route('/exportar_liquidaciones/<string:fecha_inicio>/<string:fecha_fin>/<string:formato>')
@login_required
@permiso_requerido('rp_liquidacion')
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

        data_list = []
        for liquidacion, empleado in liquidaciones_data:
            data_list.append({
                'Cédula Empleado': empleado.cedula if empleado else 'N/A',
                'Nombre Empleado': f"{empleado.nombre} {empleado.apellido_primero} {empleado.apellido_segundo}" if empleado else 'N/A',
                'Fecha Fin Contrato': liquidacion.fecha_fin_contrato.strftime('%Y-%m-%d') if liquidacion.fecha_fin_contrato else 'N/A',
                'Fecha Pago': liquidacion.fecha_pago.strftime('%Y-%m-%d') if liquidacion.fecha_pago else 'N/A',
                'Monto Total': float(f"{liquidacion.total_monto:.2f}") if liquidacion.total_monto is not None else 0.0,
                'Preaviso': float(f"{liquidacion.monto_preaviso:.2f}") if liquidacion.monto_preaviso is not None else 0.0,
                'Cesantía': float(f"{liquidacion.monto_cesantia:.2f}") if liquidacion.monto_cesantia is not None else 0.0,
                'Vacaciones': float(f"{liquidacion.monto_vacaciones:.2f}") if liquidacion.monto_vacaciones is not None else 0.0,
                'Aguinaldo': float(f"{liquidacion.monto_aguinaldo:.2f}") if liquidacion.monto_aguinaldo is not None else 0.0,
                'Salario Pendiente': float(f"{liquidacion.monto_salario_pendiente:.2f}") if liquidacion.monto_salario_pendiente is not None else 0.0
            })
        df = pd.DataFrame(data_list)
        
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
            columnas_a_formatear = ['Monto Total', 'Preaviso', 'Cesantía', 'Vacaciones', 'Aguinaldo', 'Salario Pendiente']
            
            for col in columnas_a_formatear:
                df[col] = df[col].apply(lambda x: format_currency_es(x) if isinstance(x, (int, float)) else x)

            rows = []
            for index, r in df.iterrows():
                rows.append([
                    str(r['Nombre Empleado']),
                    str(r['Fecha Pago']),
                    str(r['Cédula Empleado']),
                    str(r['Monto Total']),
                    str(r['Vacaciones']),
                    str(r['Salario Pendiente'])
                ])
            
            pdf_bytes = build_pdf_from_rows(
                title='Reporte de Liquidaciones',
                rows=rows,
                metadata={'Período': f'{fecha_inicio} a {fecha_fin}'},
                headers=["Empleado", "Fecha Pago", "Cédula", "Monto Total", "Vacaciones", "Salario Pendiente"]
            )
            pdf_buffer = io.BytesIO(pdf_bytes)
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
        return redirect(url_for('reportes_bp.mostrar_reporte_liquidaciones'))
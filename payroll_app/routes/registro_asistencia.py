from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from payroll_app.models import db, RegistroAsistencia, Feriado, Empleado, Nomina, TipoNomina, Tipo_AP, Accion_Personal
from datetime import datetime, date, time, timedelta

# El nombre del blueprint es 'registro_asistencia'
registro_asistencia_bp = Blueprint('registro_asistencia', __name__)

@registro_asistencia_bp.route('/asistencia', methods=['GET'])
@login_required 
def ver_asistencia():
    return render_template('registro_asistencia.html')

@registro_asistencia_bp.route('/asistencia/registrar', methods=['POST'])
@login_required 
def registrar_asistencia():
    empleado = Empleado.query.filter_by(Usuario_id_usuario=current_user.id_usuario).first()

    if not empleado:
        flash('No se encontró el empleado asociado a tu cuenta. Contacta al administrador.', 'danger')
        return redirect(url_for('registro_asistencia.ver_asistencia'))
    
    hora_cliente_str = request.form.get('hora_cliente')
    fecha_cliente_str = request.form.get('fecha_cliente')

    if not hora_cliente_str or not fecha_cliente_str:
        flash('Datos de hora o fecha no recibidos correctamente.', 'danger')
        return redirect(url_for('registro_asistencia.ver_asistencia'))

    try:
        fecha_registro_cliente = datetime.strptime(fecha_cliente_str, '%Y-%m-%d').date()
        hora_registro_cliente = datetime.strptime(hora_cliente_str, '%H:%M:%S').time()

        registro_de_hoy = RegistroAsistencia.query.filter_by(
            Empleado_id_empleado=empleado.id_empleado,
            hora_salida=None
        ).order_by(RegistroAsistencia.fecha_registro.desc()).first()

        if registro_de_hoy:
            if registro_de_hoy.hora_salida:
                flash('Ya has marcado tu entrada y salida hoy.', 'warning')
            else:
                registro_de_hoy.hora_salida = hora_registro_cliente

                HORA_NOMINAL_ESTANDAR = 8.0
                
                dt_entrada = datetime.combine(registro_de_hoy.fecha_registro, registro_de_hoy.hora_entrada)
                dt_salida = datetime.combine(registro_de_hoy.fecha_registro, registro_de_hoy.hora_salida)

                if dt_salida < dt_entrada:
                    dt_salida += timedelta(days=1)

                total_time_delta = dt_salida - dt_entrada
                registro_de_hoy.total_horas = round(total_time_delta.total_seconds() / 3600, 2)
                
                es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=fecha_registro_cliente).first()
                registro_de_hoy.Feriado_id_feriado = es_feriado_hoy.id_feriado if es_feriado_hoy else None
                
                horas_nominales_trabajadas = min(registro_de_hoy.total_horas, HORA_NOMINAL_ESTANDAR)
                registro_de_hoy.hora_extra = max(0, registro_de_hoy.total_horas - HORA_NOMINAL_ESTANDAR)
                registro_de_hoy.hora_feriado = 0

                horas_mensuales = 30 * HORA_NOMINAL_ESTANDAR
                costo_por_hora_normal = empleado.salario_base / horas_mensuales if horas_mensuales else 0
                costo_por_hora_extra = costo_por_hora_normal * 1.5
                costo_por_hora_feriado = costo_por_hora_normal * 2

                # ❗ Lógica de pago de feriado actualizada
                if es_feriado_hoy and es_feriado_hoy.pago_obligatorio:
                    # Pagar las 8 horas nominales del feriado (aunque no se trabaje)
                    monto_pago_feriado_base = HORA_NOMINAL_ESTANDAR * costo_por_hora_normal
                    registro_de_hoy.monto_pago = monto_pago_feriado_base
                    
                    # Si el empleado trabajó, pagar las horas trabajadas al doble
                    if registro_de_hoy.total_horas > 0:
                        horas_trabajadas_en_feriado = registro_de_hoy.total_horas
                        pago_por_trabajar_feriado = horas_trabajadas_en_feriado * costo_por_hora_feriado
                        registro_de_hoy.monto_pago += pago_por_trabajar_feriado

                    registro_de_hoy.hora_feriado = registro_de_hoy.total_horas
                    horas_nominales_trabajadas = 0
                    registro_de_hoy.hora_extra = 0
                else:
                    # Lógica de cálculo de pago para días normales
                    monto_pago = (horas_nominales_trabajadas * costo_por_hora_normal) + \
                                 (registro_de_hoy.hora_extra * costo_por_hora_extra) + \
                                 (registro_de_hoy.hora_feriado * costo_por_hora_feriado)
                    registro_de_hoy.monto_pago = round(monto_pago, 2)
                
                registro_de_hoy.hora_nominal = HORA_NOMINAL_ESTANDAR

                db.session.commit()
                flash('¡Salida y cálculos registrados exitosamente!', 'success')
        else:
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=fecha_registro_cliente).first()
            feriado_id = es_feriado_hoy.id_feriado if es_feriado_hoy else None
            
            nuevo_registro = RegistroAsistencia(
                Empleado_id_empleado=empleado.id_empleado,
                fecha_registro=fecha_registro_cliente,
                hora_entrada=hora_registro_cliente,
                Feriado_id_feriado=feriado_id,
                aprobacion_registro=False,
            )
            db.session.add(nuevo_registro)
            db.session.commit()
            flash('¡Entrada registrada exitosamente!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al registrar la asistencia: {str(e)}', 'danger')

    return redirect(url_for('registro_asistencia.ver_asistencia'))

#----------- Mantenimiento ------------------------------

# listar registros
@registro_asistencia_bp.route('/listar_asistencia')
@login_required
def listar_asistencia():
    # Obtener todos los registros de asistencia ordenados por fecha
    registros = RegistroAsistencia.query.order_by(RegistroAsistencia.fecha_registro.desc()).all()
    return render_template('listar_asistencia.html', registros=registros)

# Editar registro de asistencia
@registro_asistencia_bp.route('/editar/<int:registro_id>', methods=['GET', 'POST'])
@login_required
def editar_asistencia(registro_id):
    registro = RegistroAsistencia.query.get_or_404(registro_id)

    if request.method == 'POST':
        try:
            registro.fecha_registro = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
            registro.hora_entrada = datetime.strptime(request.form['hora_entrada'], '%H:%M:%S').time()
            registro.hora_salida = datetime.strptime(request.form['hora_salida'], '%H:%M:%S').time()
            registro.aprobacion_registro = 'aprobado' in request.form
            
            # Recalcular todos los valores (total_horas, hora_extra, monto_pago)
            HORA_NOMINAL_ESTANDAR = 8.0
            dt_entrada = datetime.combine(registro.fecha_registro, registro.hora_entrada)
            dt_salida = datetime.combine(registro.fecha_registro, registro.hora_salida)

            if dt_salida < dt_entrada:
                dt_salida += timedelta(days=1)
            
            total_time_delta = dt_salida - dt_entrada
            registro.total_horas = round(total_time_delta.total_seconds() / 3600, 2)
            
            empleado = Empleado.query.get(registro.Empleado_id_empleado)
            
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=registro.fecha_registro).first()
            registro.Feriado_id_feriado = es_feriado_hoy.id_feriado if es_feriado_hoy else None
            
            horas_nominales_trabajadas = min(registro.total_horas, HORA_NOMINAL_ESTANDAR)
            registro.hora_extra = max(0, registro.total_horas - HORA_NOMINAL_ESTANDAR)
            registro.hora_feriado = 0

            horas_mensuales = 30 * HORA_NOMINAL_ESTANDAR
            costo_por_hora_normal = empleado.salario_base / horas_mensuales if horas_mensuales else 0
            costo_por_hora_extra = costo_por_hora_normal * 1.5
            costo_por_hora_feriado = costo_por_hora_normal * 2

            if es_feriado_hoy and es_feriado_hoy.pago_obligatorio:
                # 1. Pago base del feriado (salario de un día normal, 8 horas)
                pago_base_feriado = HORA_NOMINAL_ESTANDAR * costo_por_hora_normal
                
                # 2. Pago adicional por las horas trabajadas en el feriado (al doble)
                pago_por_trabajar_feriado = registro.total_horas * costo_por_hora_feriado
                
                # 3. El monto total es la suma de ambos pagos
                registro.monto_pago = round(pago_base_feriado + pago_por_trabajar_feriado, 2)
                
                # Se ajustan las horas para reflejar que se trabajaron en un feriado
                registro.hora_feriado = registro.total_horas
                registro.hora_extra = 0
                horas_nominales_trabajadas = 0

            else:
                # Lógica para días normales y feriados de pago no obligatorio
                monto_pago = (horas_nominales_trabajadas * costo_por_hora_normal) + \
                            (registro.hora_extra * costo_por_hora_extra) + \
                            (registro.hora_feriado * costo_por_hora_feriado)
                registro.monto_pago = round(monto_pago, 2)

            db.session.commit()
            flash('Registro de asistencia actualizado exitosamente.', 'success')
            return redirect(url_for('registro_asistencia.listar_asistencia'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al actualizar el registro: {str(e)}', 'danger')
            return redirect(url_for('registro_asistencia.listar_asistencia'))

    return render_template('editar_asistencia.html', registro=registro)

#Eliminar registro
@registro_asistencia_bp.route('/eliminar/<int:registro_id>', methods=['POST'])
@login_required
def eliminar_asistencia(registro_id):
    registro = RegistroAsistencia.query.get_or_404(registro_id)

    try:
        db.session.delete(registro)
        db.session.commit()
        flash('Registro de asistencia eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al eliminar el registro: {str(e)}', 'danger')

    return redirect(url_for('registro_asistencia.listar_asistencia'))


# -------------------------  Generar Planilla Planilla 

@registro_asistencia_bp.route('/generar_nomina', methods=['GET', 'POST'])
@login_required
def generar_nomina():
    """Muestra el formulario, la lista de nóminas, y procesa la generación."""
    tipos_nomina = TipoNomina.query.all()
    
    if request.method == 'POST':
        try:
            fecha_inicio_str = request.form.get('fecha_inicio')
            fecha_fin_str = request.form.get('fecha_fin')
            id_tipo_nomina = request.form.get('tipo_nomina_id')

            if not id_tipo_nomina:
                flash('Debe seleccionar un tipo de nómina.', 'danger')
            else:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
                
                empleados = Empleado.query.filter_by(TipoNomina_id_tipo_nomina=id_tipo_nomina).all()
                
                if not empleados:
                    flash('No se encontraron empleados para el tipo de nómina seleccionado.', 'warning')
                else:
                    for empleado in empleados:
                        total_monto_bruto = db.session.query(func.sum(RegistroAsistencia.monto_pago)).filter(
                            RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                            RegistroAsistencia.fecha_registro.between(fecha_inicio, fecha_fin)
                        ).scalar() or 0
                        
                        deducciones = total_monto_bruto * 0.105
                        monto_neto = total_monto_bruto - deducciones
                        
                        nueva_nomina = Nomina(
                            Empleado_id_empleado=empleado.id_empleado,
                            fecha_inicio=fecha_inicio,
                            fecha_fin=fecha_fin,
                            salario_bruto=round(total_monto_bruto, 2),
                            salario_neto=round(monto_neto, 2),
                            deducciones=round(deducciones, 2),
                            TipoNomina_id_tipo_nomina=id_tipo_nomina,
                            fecha_creacion=datetime.now()
                        )
                        db.session.add(nueva_nomina)
                    
                    db.session.commit()
                    flash('Nómina generada y guardada exitosamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al generar la nómina: {str(e)}', 'danger')

    # Al final de la función, recupera todas las nóminas para mostrarlas.
    # Esto se ejecuta tanto en el GET inicial como después de un POST exitoso.
    nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
    return render_template('generar_nomina.html', nominas=nominas, tipos_nomina=tipos_nomina)
        
@registro_asistencia_bp.route('/listar_nominas')
@login_required
def listar_nominas():
    """Muestra una lista de todas las nóminas generadas."""
    try:
        nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
        tipos_nomina = TipoNomina.query.all()
        return render_template('generar_nomina.html', nominas=nominas, tipos_nomina=tipos_nomina)
    except Exception as e:
        flash(f'Ocurrió un error al cargar las nóminas: {str(e)}', 'danger')
        tipos_nomina = TipoNomina.query.all()
        return render_template('generar_nomina.html', nominas=[], tipos_nomina=tipos_nomina)
    

@registro_asistencia_bp.route('/accion_personal', methods=['GET', 'POST'])
@login_required
def accion_personal():
    # Fetch all employees and action types for the dropdowns
    empleados = Empleado.query.all()
    tipos_ap = Tipo_AP.query.all()

    if request.method == 'POST':
        try:
            # Get data from the form
            empleado_id = request.form.get('empleado_id')
            tipo_ap_id = request.form.get('tipo_ap_id')
            fecha_accion_str = request.form.get('fecha_accion')
            detalles = request.form.get('detalles')

            # Validate input
            if not all([empleado_id, tipo_ap_id, fecha_accion_str]):
                flash('Todos los campos son obligatorios.', 'danger')
                return render_template('accion_personal.html', empleados=empleados, tipos_ap=tipos_ap)
            
            # Convert date string to a date object
            fecha_accion = datetime.strptime(fecha_accion_str, '%Y-%m-%d').date()

            # Create a new personal action object
            nueva_ap = Accion_Personal(
                Empleado_id_empleado=empleado_id,
                Tipo_AP_id_tipo_ap=tipo_ap_id,
                fecha_accion=fecha_accion,
                detalles=detalles
            )
            db.session.add(nueva_ap)
            db.session.commit()
            
            flash('Acción de personal registrada exitosamente.', 'success')
            return redirect(url_for('registro_asistencia.accion_personal'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al registrar la acción de personal: {str(e)}', 'danger')

    # For both GET and POST (after processing), render the template
    acciones_personales = Accion_Personal.query.order_by(Accion_Personal.fecha_accion.desc()).all()
    return render_template('accion_personal.html', empleados=empleados, tipos_ap=tipos_ap, acciones_personales=acciones_personales)

@registro_asistencia_bp.route('/aprobar_accion/<int:ap_id>', methods=['POST'])
@login_required
def aprobar_accion(ap_id):
    # Obtiene la acción de personal por su ID
    ap = Accion_Personal.query.get_or_404(ap_id)
    
    # Aquí, deberías tener una lógica para verificar si el usuario tiene permisos
    # Este es un ejemplo simple, asumiendo un rol de 'aprobador'
    if current_user.rol == 'aprobador':
        ap.estado_ap = 2  # 2 = 'Aprobado'
        ap.id_aprobador = current_user.id_usuario  # Registra quién aprobó
        ap.fecha_aprobacion = datetime.utcnow()
        
        try:
            db.session.commit()
            flash('Acción de personal aprobada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al aprobar la acción: {str(e)}', 'danger')
    else:
        flash('No tienes permiso para aprobar acciones de personal.', 'danger')
        
    return redirect(url_for('registro_asistencia.accion_personal'))

@registro_asistencia_bp.route('/rechazar_accion/<int:ap_id>', methods=['POST'])
@login_required
def rechazar_accion(ap_id):
    ap = Accion_Personal.query.get_or_404(ap_id)
    
    # Asume la misma verificación de permisos
    if current_user.rol == 'aprobador':
        ap.estado_ap = 3  # 3 = 'Rechazado'
        ap.id_aprobador = current_user.id_usuario
        ap.fecha_aprobacion = datetime.utcnow()
        
        try:
            db.session.commit()
            flash('Acción de personal rechazada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al rechazar la acción: {str(e)}', 'danger')
    else:
        flash('No tienes permiso para rechazar acciones de personal.', 'danger')
        
    return redirect(url_for('registro_asistencia.accion_personal'))
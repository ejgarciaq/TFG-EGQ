from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from payroll_app.models import db, RegistroAsistencia, Feriado, Empleado
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
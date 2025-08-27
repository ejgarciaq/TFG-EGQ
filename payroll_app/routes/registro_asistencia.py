from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from payroll_app.models import db, RegistroAsistencia, Feriado
from datetime import datetime

registro_asistencia_bp = Blueprint('registro_asistencia', __name__, template_folder='templates')

@registro_asistencia_bp.route('/asistencia', methods=['GET'])
@login_required
def ver_asistencia():
    # Esta ruta simplemente muestra el formulario HTML
    return render_template('registro_asistencia.html')

@registro_asistencia_bp.route('/asistencia/registrar', methods=['POST'])
@login_required
def registrar_asistencia():
    # Obtener el objeto de usuario y empleado del usuario actual
    empleado = current_user.empleado
    if not empleado:
        flash('No se encontró el empleado asociado al usuario.', 'danger')
        return redirect(url_for('asistencia.ver_asistencia'))

    # Verificar si ya existe un registro de entrada para hoy
    registro_de_hoy = RegistroAsistencia.query.filter_by(
        Empleado_id_empleado=empleado.id_empleado,
        fecha_registro=datetime.utcnow().date()
    ).first()

    try:
        if registro_de_hoy:
            # Caso 2: El empleado ya marcó su entrada y ahora está marcando la salida
            if registro_de_hoy.hora_salida:
                flash('Ya has marcado tu entrada y salida hoy.', 'warning')
            else:
                registro_de_hoy.hora_salida = datetime.utcnow().time()
                db.session.commit()
                flash('¡Salida registrada exitosamente!', 'success')
        else:
            # Caso 1: El empleado está marcando su entrada por primera vez hoy
            
            # Verificar si es feriado
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=datetime.utcnow().date()).first()

            nuevo_registro = RegistroAsistencia(
                Empleado_id_empleado=empleado.id_empleado,
                Empleado_Usuario_id_usuario=empleado.Usuario_id_usuario,
                fecha_registro=datetime.utcnow().date(),
                hora_entrada=datetime.utcnow().time(),
                hora_salida=None,  # No hay hora de salida aún
                estado_feriado=1 if es_feriado_hoy else 0,
                aprobacion_registro=0, # Pendiente de aprobación
                # Los demás campos (horas_extra, etc.) se calculan y llenan más tarde
            )
            db.session.add(nuevo_registro)
            db.session.commit()
            flash('¡Entrada registrada exitosamente!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al registrar la asistencia: {str(e)}', 'danger')

    return redirect(url_for('asistencia.ver_asistencia'))
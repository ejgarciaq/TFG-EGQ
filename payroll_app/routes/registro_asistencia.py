from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from payroll_app.models import db, RegistroAsistencia, Feriado, Empleado
from datetime import datetime, date, time

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
    
    # ❗ Obtener la hora y la fecha del formulario que el cliente envió
    hora_cliente_str = request.form.get('hora_cliente')
    fecha_cliente_str = request.form.get('fecha_cliente')

    if not hora_cliente_str or not fecha_cliente_str:
        flash('Datos de hora o fecha no recibidos correctamente.', 'danger')
        return redirect(url_for('registro_asistencia.ver_asistencia'))

    try:
        # Convertir las cadenas de texto a objetos de Python
        fecha_registro = datetime.strptime(fecha_cliente_str, '%Y-%m-%d').date()
        hora_registro = datetime.strptime(hora_cliente_str, '%H:%M:%S').time()

        registro_de_hoy = RegistroAsistencia.query.filter_by(
            Empleado_id_empleado=empleado.id_empleado,
            fecha_registro=fecha_registro
        ).first()

        if registro_de_hoy:
            # Lógica para registrar la hora de salida
            if registro_de_hoy.hora_salida:
                flash('Ya has marcado tu entrada y salida hoy.', 'warning')
            else:
                registro_de_hoy.hora_salida = hora_registro
                db.session.commit()
                flash('¡Salida registrada exitosamente!', 'success')
        else:
            # Lógica para registrar la hora de entrada
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=fecha_registro).first()
            
            nuevo_registro = RegistroAsistencia(
                Empleado_id_empleado=empleado.id_empleado,
                fecha_registro=fecha_registro,
                hora_entrada=hora_registro,
                estado_feriado=True if es_feriado_hoy else False,
                aprobacion_registro=False,
            )
            db.session.add(nuevo_registro)
            db.session.commit()
            flash('¡Entrada registrada exitosamente!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al registrar la asistencia: {str(e)}', 'danger')

    return redirect(url_for('registro_asistencia.ver_asistencia'))

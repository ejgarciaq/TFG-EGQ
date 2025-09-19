from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from payroll_app.models import db, Feriado
from datetime import datetime
from payroll_app.routes.decorators import permiso_requerido

feriado_bp = Blueprint('feriado', __name__)

# Listar feriados ---------------------------------------------
@feriado_bp.route('/listar_feriado')
@permiso_requerido('listar_feriado')
@login_required
def listar_feriados():
    feriados = Feriado.query.order_by(Feriado.fecha_feriado).all()
    return render_template('feriado.html', feriados=feriados)

# Agregar feriados -----------------------------------------------
@feriado_bp.route('/agregar_feriados', methods=['POST'])
@permiso_requerido('crear_feriados')
@login_required
def agregar_feriado():
    fecha_str = request.form.get('fecha_feriado')
    descripcion = request.form.get('descripcion_feriado')
    pago_obligatorio_str = request.form.get('pago_obligatorio')
    pago_obligatorio = True if pago_obligatorio_str == 'on' else False

    if not fecha_str or not descripcion:
        flash('Por favor, ingresa una fecha y una descripción para el feriado.', 'danger')
        return redirect(url_for('feriado.listar_feriados'))

    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        feriado_existente = Feriado.query.filter_by(fecha_feriado=fecha).first()
        if feriado_existente:
            flash(f'El feriado en la fecha {fecha_str} ya existe.', 'warning')
            return redirect(url_for('feriado.listar_feriados'))

        nuevo_feriado = Feriado(fecha_feriado=fecha, descripcion_feriado=descripcion, pago_obligatorio=pago_obligatorio)
        db.session.add(nuevo_feriado)
        db.session.commit()
        flash('Feriado agregado exitosamente.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al agregar el feriado: {e}', 'danger')

    return redirect(url_for('feriado.listar_feriados'))

# Editar feriado -------------------------------------------------------------------------
@feriado_bp.route('/editar_feriado/<int:id_feriado>', methods=['GET', 'POST'])
@permiso_requerido('editar_feriado')
@login_required
def editar_feriado(id_feriado):
    feriado = Feriado.query.get_or_404(id_feriado)
    if request.method == 'POST':
        try:
            feriado.fecha_feriado = datetime.strptime(request.form.get('fecha_feriado'), '%Y-%m-%d').date()
            feriado.descripcion_feriado = request.form.get('descripcion_feriado')
            pago_obligatorio_str = request.form.get('pago_obligatorio')
            feriado.pago_obligatorio = True if pago_obligatorio_str == 'on' else False
            
            db.session.commit()
            flash('Feriado actualizado exitosamente.', 'success')
            return redirect(url_for('feriado.listar_feriados'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al editar el feriado: {e}', 'danger')
    
    return render_template('editar_feriado.html', feriado=feriado)

# Eliminar feriado -------------------------------------------------------------
@feriado_bp.route('/eliminar_feriado/<int:id_feriado>', methods=['POST'])
@permiso_requerido('eliminar_feriado')
@login_required
def eliminar_feriado(id_feriado):
    feriado = Feriado.query.get_or_404(id_feriado)
    try:
        db.session.delete(feriado)
        db.session.commit()
        flash('Feriado eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al eliminar el feriado: {e}', 'danger')
        
    return redirect(url_for('feriado.listar_feriados'))
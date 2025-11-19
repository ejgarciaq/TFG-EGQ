from flask import Blueprint, render_template, request, redirect, url_for, flash
from payroll_app.models import Puesto
from payroll_app import db
from flask_login import current_user, login_required
from payroll_app.routes.decorators import permiso_requerido

""" Blueprint para la gestión de puestos. """
puesto_bp = Blueprint('puesto', __name__)

""" Muestra una lista de todos los puestos. """
@puesto_bp.route('/puestos')
@permiso_requerido('listar_puestos')
@login_required
def listar_puestos():
    # Obtiene el número de página de la URL, por defecto es 1
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Define el número de registros por página

    # Crea la consulta base, ordenada por el ID del puesto
    query = Puesto.query.order_by(Puesto.id_puesto.asc())

    # Aplica la paginación a la consulta ordenada
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template('puesto/listar_puestos.html', pagination=pagination)

""" Crea un nuevo puesto. """
@puesto_bp.route('/puestos/crear', methods=['GET', 'POST'])
@permiso_requerido('crear_puesto')
@login_required
def crear_puesto():
    if request.method == 'POST':
        tipo_puesto = request.form['tipo_puesto']

        # Verificar si el puesto ya existe
        puesto_existente = Puesto.query.filter_by(tipo_puesto=tipo_puesto).first()
        if puesto_existente:
            flash('Este puesto ya existe. Por favor, ingrese un nombre diferente.', 'danger')
            return redirect(url_for('puesto.crear_puesto'))

        nuevo_puesto = Puesto(tipo_puesto=tipo_puesto)
        db.session.add(nuevo_puesto)

        try:
            db.session.commit()
            flash('Puesto creado exitosamente.', 'success')
            return redirect(url_for('puesto.listar_puestos'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear el puesto: {e}', 'danger')
            return redirect(url_for('puesto.crear_puesto'))
    
    return render_template('puesto/crear_puesto.html'
                           )

""" Edita un puesto existente."""
@puesto_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@permiso_requerido('editar_puesto')
@login_required
def editar_puesto(id):
    puesto_a_editar = Puesto.query.get_or_404(id)

    if request.method == 'POST':
        tipo_puesto = request.form['tipo_puesto']
        page = request.form.get('page', 1, type=int)
        
        puesto_existente = Puesto.query.filter(Puesto.tipo_puesto == tipo_puesto, Puesto.id_puesto != id).first()
        if puesto_existente:
            flash('Este puesto ya existe. Por favor, ingrese un nombre diferente.', 'danger')
            return redirect(url_for('puesto.editar_puesto', id=id, page=page))
        
        puesto_a_editar.tipo_puesto = tipo_puesto
        
        try:
            db.session.commit()
            flash('Puesto actualizado exitosamente.', 'success')
            return redirect(url_for('puesto.listar_puestos', page=page))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el puesto: {e}', 'danger')
            return redirect(url_for('puesto.editar_puesto', id=id, page=page))

    page = request.args.get('page', 1, type=int)
    return render_template('puesto/editar_puesto.html', puesto=puesto_a_editar, page=page)

""" Elimina un puesto existente."""
@puesto_bp.route('/puestos/eliminar/<int:id>', methods=['POST'])
@permiso_requerido('eliminar_puesto')
@login_required
def eliminar_puesto(id):
    puesto_a_eliminar = Puesto.query.get_or_404(id)
    db.session.delete(puesto_a_eliminar)
    
    try:
        db.session.commit()
        flash('Puesto eliminado exitosamente.', 'success')
        return redirect(url_for('puesto.listar_puestos'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el puesto: {e}', 'danger')
        return redirect(url_for('puesto.listar_puestos'))
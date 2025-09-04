from flask import Blueprint, render_template, request, redirect, url_for, flash
from payroll_app.models import Puesto
from payroll_app import db
from flask_login import login_required

puesto_bp = Blueprint('puesto', __name__)

@puesto_bp.route('/puestos')
def listar_puestos():
    """Muestra una lista de todos los puestos."""
    # ❗❗❗ CORRECCIÓN: Ordenar los puestos por su ID de forma ascendente ❗❗❗
    puestos = Puesto.query.order_by(Puesto.id_puesto.asc()).all()
    return render_template('listar_puestos.html', puestos=puestos)

@puesto_bp.route('/puestos/crear', methods=['GET', 'POST'])
def crear_puesto():
    """Crea un nuevo puesto."""
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
    
    return render_template('crear_puesto.html')

@puesto_bp.route('/puestos/editar/<int:id>', methods=['GET', 'POST'])
def editar_puesto(id):
    """Edita un puesto existente."""
    puesto_a_editar = Puesto.query.get_or_404(id)

    if request.method == 'POST':
        tipo_puesto = request.form['tipo_puesto']

        # Verificar si el nuevo nombre de puesto ya existe, excluyendo el actual
        puesto_existente = Puesto.query.filter(Puesto.tipo_puesto == tipo_puesto, Puesto.id_puesto != id).first()
        if puesto_existente:
            flash('Este puesto ya existe. Por favor, ingrese un nombre diferente.', 'danger')
            return redirect(url_for('puesto.editar_puesto', id=id))
        
        puesto_a_editar.tipo_puesto = tipo_puesto
        
        try:
            db.session.commit()
            flash('Puesto actualizado exitosamente.', 'success')
            return redirect(url_for('puesto.listar_puestos'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el puesto: {e}', 'danger')
            return redirect(url_for('puesto.editar_puesto', id=id))

    return render_template('editar_puesto.html', puesto=puesto_a_editar)

@puesto_bp.route('/puestos/eliminar/<int:id>', methods=['POST'])
def eliminar_puesto(id):
    """Elimina un puesto existente."""
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
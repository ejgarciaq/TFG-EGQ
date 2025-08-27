# payroll_app/routes/rol.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from payroll_app.models import db, Rol

rol_bp = Blueprint('rol', __name__, url_prefix='/roles')

@rol_bp.route('/')
def listar_roles():
    """Muestra una lista de todos los roles existentes."""
    roles = Rol.query.all() # Obtener todos los roles de la base de datos
    return render_template('listar_roles.html', roles=roles) # Renderizar la plantilla con la lista de roles

@rol_bp.route('/crear', methods=['GET', 'POST'])
def crear_rol():
    """Muestra el formulario para crear un nuevo rol y lo procesa."""
    if request.method == 'POST':
        tipo_rol = request.form.get('tipo_rol') # Obtener el nombre del rol del formulari
        descripcion_rol = request.form.get('descripcion_rol') # Obtener la descripción del formulario
        if tipo_rol and descripcion_rol:
            nuevo_rol = Rol(tipo_rol=tipo_rol, descripcion_rol=descripcion_rol) # Crear una nueva instancia de Rol
            db.session.add(nuevo_rol)
            db.session.commit()
            flash('Rol creado exitosamente.', 'success')
            return redirect(url_for('rol.listar_roles'))
        else:
            flash('El nombre del rol no puede estar vacío.', 'error')
    
    return render_template('crear_rol.html')

@rol_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar_rol(id):
    """Muestra el formulario para editar un rol y procesa la actualización."""
    rol_a_editar = Rol.query.get_or_404(id)

    if request.method == 'POST':
        # Recupera los datos del formulario, incluyendo la descripción
        tipo_rol = request.form['tipo_rol']
        descripcion_rol = request.form.get('descripcion_rol')

        # Actualiza el objeto Rol
        rol_a_editar.tipo_rol = tipo_rol
        rol_a_editar.descripcion_rol = descripcion_rol

        try:
            db.session.commit()
            flash('Rol actualizado exitosamente', 'success')
            return redirect(url_for('rol.listar_roles'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el rol: {e}', 'danger')
            return redirect(url_for('rol.editar_rol', id=id))

    # Si el método es GET, simplemente renderiza la plantilla con los datos del rol
    return render_template('editar_rol.html', rol=rol_a_editar)

@rol_bp.route('/eliminar/<int:id>', methods=['POST'])
def eliminar_rol(id):
    """Elimina un rol de la base de datos."""
    rol = Rol.query.get_or_404(id)
    db.session.delete(rol)
    db.session.commit()
    flash('Rol eliminado exitosamente.', 'success')
    return redirect(url_for('rol.listar_roles'))

        
     
from flask import Blueprint, render_template, request, redirect, url_for, flash
from payroll_app.models import db,Rol

rol_bp = Blueprint('rol', __name__, url_prefix='/roles') # Crea un blueprint para las rutas de rol

@rol_bp.route('/')
def listar_roles():
    # Listar todos los roles
    roles = Rol.query.all()
    return render_template('listar_roles.html', roles=roles)

@rol_bp.route('/crear', methods=['GET', 'POST'])
def crear_rol():
    # Crear un nuevo rol
    if request.method == 'POST':
        tipo_rol = request.form.get('tipo_rol')
        nuevo_rol = Rol(tipo_rol=tipo_rol)
        db.session.add(nuevo_rol)
        db.session.commit()
        flash('Rol creado exitosamente.', 'success')
        return redirect(url_for('rol.listar_roles'))
    return render_template('crear_rol.html')

@rol_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar_rol(id):
    """Muestra el formulario para editar un rol y procesa la actualización."""
    rol = Rol.query.get_or_404(id)
    if request.method == 'POST':
        rol.tipo_rol = request.form.get('tipo_rol')
        db.session.commit()
        flash('Rol actualizado exitosamente.', 'success')
        return redirect(url_for('rol.listar_roles'))
        
    return render_template('editar_rol.html', rol=rol)

@rol_bp.route('/eliminar/<int:id>', methods=['POST'])
def eliminar_rol(id):
    """Elimina un rol de la base de datos."""
    rol = Rol.query.get_or_404(id)
    db.session.delete(rol)
    db.session.commit()
    flash('Rol eliminado exitosamente.', 'success')
    return redirect(url_for('rol.listar_roles'))

        
     
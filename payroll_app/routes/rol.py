from flask import Blueprint, render_template, request, redirect, url_for, flash
from payroll_app.routes.decorators import permiso_requerido, admin_required # ✅ Importa el nuevo decorador
from payroll_app.models import db, Rol, Permiso, Usuario # ✅ Asegúrate de importar Permiso
from flask_login import current_user, login_required

rol_bp = Blueprint('rol', __name__, url_prefix='/roles')

@rol_bp.route('/')
@permiso_requerido('listar_roles') # Protege la ruta con un permiso específico
@login_required
def listar_roles():
    """
    Muestra una lista de todos los roles existentes.
    Requiere el permiso 'listar_roles'.
    """
    roles = Rol.query.all()
    return render_template('listar_roles.html', roles=roles)

@rol_bp.route('/crear', methods=['GET', 'POST'])
@permiso_requerido('crear_rol') # Protege la ruta con el permiso 'crear_rol'
@login_required
def crear_rol():
    """
    Muestra el formulario para crear un nuevo rol y lo procesa.
    Permite asociar permisos al nuevo rol.
    """
    # Obtiene todos los permisos de la base de datos para mostrarlos en el formulario.
    permisos = Permiso.query.all()
    
    if request.method == 'POST':
        tipo_rol = request.form.get('tipo_rol')
        descripcion_rol = request.form.get('descripcion_rol')
        # ✅ Obtiene la lista de IDs de los permisos seleccionados en el formulario.
        permisos_seleccionados_ids = request.form.getlist('permisos')
        
        if tipo_rol and descripcion_rol:
            nuevo_rol = Rol(tipo_rol=tipo_rol, descripcion_rol=descripcion_rol)
            
            # ✅ Asocia los permisos seleccionados al nuevo rol.
            for permiso_id in permisos_seleccionados_ids:
                permiso = Permiso.query.get(permiso_id)
                if permiso:
                    nuevo_rol.permisos.append(permiso)
            
            db.session.add(nuevo_rol)
            db.session.commit()
            flash('Rol creado exitosamente.', 'success')
            return redirect(url_for('rol.listar_roles'))
        else:
            flash('El nombre y la descripción del rol no pueden estar vacíos.', 'error')
    
    return render_template('crear_rol.html', permisos=permisos)

@rol_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@permiso_requerido('editar_rol') # Protege la ruta con el permiso 'editar_rol'
@login_required
def editar_rol(id):
    """
    Muestra el formulario para editar un rol y procesa la actualización.
    Permite modificar los permisos asociados al rol.
    """
    rol_a_editar = Rol.query.get_or_404(id)
    # Obtiene todos los permisos para mostrarlos en el formulario de edición.
    permisos = Permiso.query.all()

    if request.method == 'POST':
        tipo_rol = request.form['tipo_rol']
        descripcion_rol = request.form.get('descripcion_rol')
        # Obtiene la lista de IDs de los permisos seleccionados.
        permisos_seleccionados_ids = request.form.getlist('permisos')

        rol_a_editar.tipo_rol = tipo_rol
        rol_a_editar.descripcion_rol = descripcion_rol
        
        # Primero, limpia los permisos existentes del rol.
        rol_a_editar.permisos.clear()
        # Luego, agrega los permisos seleccionados.
        for permiso_id in permisos_seleccionados_ids:
            permiso = Permiso.query.get(permiso_id)
            if permiso:
                rol_a_editar.permisos.append(permiso)

        try:
            db.session.commit()
            flash('Rol actualizado exitosamente', 'success')
            return redirect(url_for('rol.listar_roles'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el rol: {e}', 'danger')
            return redirect(url_for('rol.editar_rol', id=id))

    # Si el método es GET, renderiza la plantilla con los datos del rol y los permisos.
    return render_template('editar_rol.html', rol=rol_a_editar, permisos=permisos)

@rol_bp.route('/eliminar/<int:id>', methods=['POST'])
@permiso_requerido('eliminar_rol') # Protege la ruta con el permiso 'eliminar_rol'
@login_required
def eliminar_rol(id):
    """
    Elimina un rol de la base de datos.
    Requiere el permiso 'eliminar_rol'.
    """
    rol = Rol.query.get_or_404(id)
    
    # Lógica de seguridad para evitar la eliminación de roles críticos.
    if rol.tipo_rol in ['Administrador', 'Empleado']:
        flash('No se puede eliminar un rol del sistema.', 'danger')
    else:
        db.session.delete(rol)
        db.session.commit()
        flash('Rol eliminado exitosamente.', 'success')
    
    return redirect(url_for('rol.listar_roles'))
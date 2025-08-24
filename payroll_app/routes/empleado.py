from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
from payroll_app.models import db, Usuario, Rol, Empleado, Puesto
from datetime import datetime

empleado_bp = Blueprint('empleado', __name__, template_folder='templates') # Crea un blueprint para las rutas de empleado

@empleado_bp.route('/crear_empleado', methods=['GET', 'POST'])
def crear_empleado():
    # obtener lista de roles y puestos para el formulario
    roles = Rol.query.all()
    puestos = Puesto.query.all()

    if request.method == 'POST':
        # Procesar el formulario de creación de empleado
        try:
            username = request.form['username']
            if Usuario.query.filter_by(username=username).first():
                flash('El nombre de usuario ya existe. Por favor, elige otro.', 'error')
                return redirect(url_for('empleado.crear_empleado'))

            # Crear el usuario
            password = generate_password_hash(request.form['password']) # Hashear la contraseña
            nuevo_usuario = Usuario(
                username=username,
                password=password,
                estado_usuario=True,
                Rol_id_rol=request.form['rol_id']
            )
            db.session.add(nuevo_usuario)
            db.session.commit()

            # Crear el empleado
            fecha_ingreso = datetime.strptime(request.form['fecha_ingreso'], '%Y-%m-%d').date()
            nuevo_empleado = Empleado(
                nombre=request.form['nombre'],
                apellido_primero=request.form['apellido_primero'],
                apellido_segundo=request.form.get('apellido_segundo'),
                cedula=request.form['cedula'],
                correo=request.form['correo'],
                telefono=request.form['telefono'],
                fecha_ingreso=fecha_ingreso,
                fecha_salida=None,
                salario_base=float(request.form['salario_base']),
                estado_empleado=True,
                Puesto_id_puesto=request.form['puesto_id'],
                Usuario_id_usuario=nuevo_usuario.id_usuario
            )
            db.session.add(nuevo_empleado)
            db.session.commit()

            flash('Empleado creado exitosamente.', 'success')
            return redirect(url_for('empleado.listar_empleado'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear el empleado: {str(e)}', 'error')
            
    return render_template('crear_empleado.html', puestos=puestos, roles=roles)
    
@empleado_bp.route('/listar_empleado')
def listar_empleado():
    # Listar todos los empleados
    empleados = Empleado.query.all()
    return render_template('listar_empleado.html', empleados=empleados)

@empleado_bp.route('/editar_empleado/<int:id>', methods=['GET', 'POST'])
def editar_empleado(id):
    # Editar un empleado existente
    empleado = Empleado.query.get_or_404(id)
    roles = Rol.query.all()
    puestos = Puesto.query.all()

    if request.method == 'POST':
        try:
            empleado.nombre = request.form['nombre']
            empleado.apellido_primero = request.form['apellido_primero']
            empleado.apellido_segundo = request.form.get('apellido_segundo')
            empleado.cedula = request.form['cedula']
            empleado.correo = request.form['correo']
            empleado.telefono = request.form['telefono']
            empleado.salario_base = float(request.form['salario_base'])
            empleado.fecha_ingreso = datetime.strptime(request.form['fecha_ingreso'], '%Y-%m-%d').date()
            empleado.fecha_salida = datetime.strptime(request.form['fecha_salida'], '%Y-%m-%d').date() if request.form['fecha_salida'] else None
            empleado.estado_empleado = request.form.get('estado_empleado') == 'on'
            empleado.Puesto_id_puesto = request.form['puesto_id']

            # Actualizar el usuario asociado
            usuario = Usuario.query.get_or_404(empleado.Usuario_id_usuario)
            usuario.username = request.form['username']
            usuario.Rol_id_rol = request.form['rol_id']
            usuario.estado_usuario = request.form.get('estado_usuario') == 'on'

            # Solo actualizar la contraseña si se proporciona una nueva
            if request.form['password']:
                usuario.password = generate_password_hash(request.form['password'])
            
            db.session.commit()
            flash('Empleado actualizado exitosamente.', 'success')
            return redirect(url_for('empleado.listar_empleado'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al actualizar el empleado: {str(e)}', 'error')

    return render_template('editar_empleado.html', empleado=empleado, roles=roles, puestos=puestos)

@empleado_bp.route('/eliminar_empleado/<int:id>', methods=['POST'])
def eliminar_empleado(id):
    # Eliminar un empleado
    empleado = Empleado.query.get_or_404(id)
    usuario = Usuario.query.get_or_404(empleado.Usuario_id_usuario)

    try:
        # Primero eliminar el usuario asociado
        db.session.delete(empleado)
        db.session.delete(usuario)
        db.session.commit()
        flash('Empleado eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al eliminar el empleado: {str(e)}', 'error')
    
    return redirect(url_for('empleado.listar_empleado'))

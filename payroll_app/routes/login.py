import pytz
import secrets
import string
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from payroll_app.models import Empleado, Usuario, db
from flask_login import login_user, logout_user, login_required, current_user

# Crea un Blueprint para las rutas de autenticación.
login_bp = Blueprint('auth', __name__)

# Define la zona horaria local de Costa Rica para manejar fechas y horas correctamente.
ZONA_HORARIA_LOCAL = pytz.timezone('America/Costa_Rica')

# Definir el límite de intentos y el tiempo de bloqueo de la cuenta.
MAX_INTENTOS_FALLIDOS = 5
TIEMPO_BLOQUEO_MINUTOS = 15

#-----------------------------------------------------------------------------------
# RUTAS DE AUTENTICACIÓN
#-----------------------------------------------------------------------------------

@login_bp.route('/')
def home():
    """Redirige la ruta principal a la página de login."""
    # Si el usuario ya está autenticado, lo envía a la página base.
    if current_user.is_authenticated:
        return redirect(url_for('auth.base'))
    # Si no, lo redirige a la página de inicio de sesión.
    return redirect(url_for('auth.login'))

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Si el usuario ya está autenticado, evita que acceda al formulario de login.
    if current_user.is_authenticated:
        return redirect(url_for('auth.base'))

    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            # Valida que los campos de usuario y contraseña no estén vacíos.
            if not username or not password:
                flash('Por favor, completa todos los campos', 'danger')
                return render_template('index.html')
            # Busca el usuario en la base de datos por el nombre de usuario.
            usuario = Usuario.query.filter_by(username=username).first()
            
            if usuario:
                ahora = datetime.now(ZONA_HORARIA_LOCAL)
                
                # Lógica de desbloqueo temporal:
                # Si la cuenta está inactiva (bloqueada) y ha pasado el tiempo de bloqueo,
                # la desbloquea y reinicia el contador de intentos.
                if not usuario.estado_usuario:
                    tiempo_transcurrido = ahora - usuario.fecha_ultimo_intento
                    if tiempo_transcurrido.total_seconds() >= TIEMPO_BLOQUEO_MINUTOS * 60:
                        usuario.estado_usuario = True
                        usuario.intentos_fallidos = 0
                        db.session.commit()
                        flash('Su cuenta ha sido desbloqueada. Por favor, intente iniciar sesión de nuevo.', 'success')
                        return render_template('index.html')
                    else:
                        flash('Su cuenta se encuentra temporalmente bloqueada debido a demasiados intentos fallidos. Por favor, inténtelo de nuevo más tarde.', 'danger')
                        return render_template('index.html')
                # Verifica la contraseña con la función de hash.
                if check_password_hash(usuario.password, password):
                    # Inicio de sesión exitoso:
                    # - Resetea el contador de intentos fallidos.
                    # - Inicia la sesión de usuario con Flask-Login.
                    usuario.intentos_fallidos = 0
                    usuario.fecha_ultimo_intento = ahora
                    db.session.commit()
                    login_user(usuario) 
                    flash('Inicio de sesión exitoso.', 'success')
                    
                    # Redirección condicional: si el cambio de contraseña es requerido,
                    # lo envía a la página de cambio de contraseña.
                    if usuario.cambio_password_requerido:
                        return redirect(url_for('auth.cambiar_contrasena'))
                    else:
                        return redirect(url_for('auth.base'))
                else:
                    # Contraseña incorrecta:
                    # - Incrementa el contador de intentos fallidos y actualiza la fecha.
                    usuario.intentos_fallidos += 1
                    usuario.fecha_ultimo_intento = ahora
                    db.session.commit()
                    # Si el número de intentos excede el límite, bloquea la cuenta.
                    if usuario.intentos_fallidos >= MAX_INTENTOS_FALLIDOS:
                        usuario.estado_usuario = False
                        db.session.commit()
                        flash(f'Se ha excedido el número de intentos. Su cuenta ha sido bloqueada por {TIEMPO_BLOQUEO_MINUTOS} minutos.', 'danger')
                    else:
                        flash('Nombre de usuario o contraseña incorrecta. Por favor, inténtelo de nuevo.', 'danger')
            else:
                # Usuario no encontrado.
                flash('Nombre de usuario o contraseña incorrecta. Por favor, inténtelo de nuevo.', 'danger')
        
        except Exception as e:
            # Captura y registra cualquier error inesperado para su posterior análisis.
            current_app.logger.error(f'Error en la función de login: {e}', exc_info=True)
            flash('Ocurrió un error inesperado. Por favor, intente de nuevo más tarde.', 'danger')
            return render_template('index.html')
            
    return render_template('index.html')
    
@login_bp.route('/base')
@login_required # Decorador que asegura que solo los usuarios autenticados pueden acceder a esta ruta.
def base():
    """Ruta para la página principal de la aplicación, solo accesible para usuarios autenticados."""
    return render_template('base.html')
    
@login_bp.route('/logout')
def logout():
    """Cierra la sesión del usuario actual."""
    try:
        logout_user() # Función de Flask-Login para cerrar la sesión.
        flash('Has cerrado sesión correctamente.', 'success')
        return redirect(url_for('auth.login'))
    except Exception as e:
        current_app.logger.error(f'Error al cerrar la sesión: {e}', exc_info=True)
        flash('Ocurrió un error inesperado al cerrar la sesión. Por favor, inténtelo de nuevo.', 'danger')
        return redirect(url_for('auth.base'))

@login_bp.route('/olvido_contrasena', methods=['GET'])
def olvido_contrasena():
    """Muestra la página de 'olvidó su contraseña' que redirige al administrador."""
    return render_template('olvido_contrasena.html')

@login_bp.route('/admin/restablecer_contrasena', methods=['POST']) # ✅ Cambiar a solo POST
@login_required
def restablecer_contrasena_admin():
    if not current_user.rol.tipo_rol == 'admin':
        flash('No tiene permisos para acceder a esta página.', 'danger')
        return redirect(url_for('auth.base'))

    username = request.form.get('username')
    
    # ✅ Verificar si el campo de usuario está presente
    if not username:
        flash('No se ha proporcionado un nombre de usuario.', 'danger')
        return redirect(url_for('empleado.listar_empleado')) # Redirigir a una página segura si no hay usuario
        
    usuario = Usuario.query.filter_by(username=username).first()

    # ✅ Obtener el ID del empleado antes de redirigir
    empleado = Empleado.query.filter_by(Usuario_id_usuario=usuario.id_usuario).first()
    if not empleado:
        flash('Empleado no encontrado para el usuario especificado.', 'danger')
        return redirect(url_for('empleado.listar_empleado'))

    if not usuario:
        flash(f'No se encontró ningún usuario con el nombre "{username}".', 'danger')
        return redirect(url_for('empleado.editar_empleado', id=empleado.id_empleado))

    try:
        alphabet = string.ascii_letters + string.digits + string.punctuation
        temp_password = ''.join(secrets.choice(alphabet) for i in range(8))
        
        usuario.password = generate_password_hash(temp_password)
        usuario.cambio_password_requerido = True
        db.session.commit()
        
        flash(f'La contraseña para el usuario "{username}" ha sido restablecida. La nueva clave temporal es: {temp_password}', 'success')
        
    except Exception as e:
        current_app.logger.error(f'Error al restablecer la contraseña del usuario {username}: {e}', exc_info=True)
        flash('Ocurrió un error al restablecer la contraseña. Contacta a soporte.', 'danger')
    
    # ✅ Redirigir de vuelta a la página de edición del empleado
    return redirect(url_for('empleado.editar_empleado', id=empleado.id_empleado))

@login_bp.route('/cambiar_contrasena', methods=['GET', 'POST'])
@login_required
def cambiar_contrasena():
    # Si el cambio no es requerido, redirigir a la página principal
    if not current_user.cambio_password_requerido:
        return redirect(url_for('auth.base'))
        
    if request.method == 'POST':
        nueva_contrasena = request.form.get('nueva_contrasena')
        confirmar_contrasena = request.form.get('confirmar_contrasena')
        
        if not nueva_contrasena or not confirmar_contrasena:
            flash('Por favor, completa todos los campos.', 'danger')
            return render_template('cambiar_contrasena.html')

        if nueva_contrasena != confirmar_contrasena:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('cambiar_contrasena.html')

        try:
            current_user.password = generate_password_hash(nueva_contrasena)
            current_user.cambio_password_requerido = False
            db.session.commit()
            flash('Su contraseña ha sido actualizada exitosamente.', 'success')
            return redirect(url_for('auth.base'))

        except Exception as e:
            current_app.logger.error(f'Error al cambiar la contraseña del usuario {current_user.username}: {e}', exc_info=True)
            flash('Ocurrió un error al actualizar su contraseña. Intente de nuevo.', 'danger')

    return render_template('cambiar_contrasena.html')
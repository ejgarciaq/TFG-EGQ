import pytz, secrets, string, re
from datetime import datetime, timedelta
from werkzeug.security import ( generate_password_hash, check_password_hash, )
from flask import ( Blueprint, render_template, request, redirect, url_for, flash, session, current_app, )
from payroll_app.models import ( Empleado, Usuario, db, )
from flask_login import ( login_user, logout_user, login_required, current_user )

""" Blueprint para las rutas de autenticación (login, logout, etc.)."""
login_bp = Blueprint('auth', __name__)

""" Define la zona horaria local de Costa Rica para manejar fechas y horas correctamente."""
ZONA_HORARIA_LOCAL = pytz.timezone('America/Costa_Rica')

""" Definir el límite de intentos y el tiempo de bloqueo de la cuenta. """
MAX_INTENTOS_FALLIDOS = 3
TIEMPO_BLOQUEO_MINUTOS = 15

""" Función para validar la complejidad de la contraseña. """
def validar_complejidad_password(password):
    """    
    Requisitos:
    - Mínimo 8 caracteres de longitud.
    - Al menos una letra mayúscula.
    - Al menos una letra minúscula.
    - Al menos un número.
    - Al menos un carácter especial (@$!%*?&).
    """
    # 1. Mínimo 8 caracteres
    if len(password) < 8:
        return False, 'La contraseña debe tener al menos 8 caracteres.'
    # 2. Al menos una letra mayúscula
    if not re.search(r"[A-Z]", password):
        return False, 'La contraseña debe contener al menos una letra mayúscula.'
    # 3. Al menos una letra minúscula
    if not re.search(r"[a-z]", password):
        return False, 'La contraseña debe contener al menos una letra minúscula.'
    # 4. Al menos un dígito
    if not re.search(r"[0-9]", password):
        return False, 'La contraseña debe contener al menos un número.'
    # 5. Al menos un carácter especial
    if not re.search(r"[@$!%*?&]", password):
        return False, 'La contraseña debe contener al menos uno de los siguientes caracteres especiales: @$!%*?&.'
    
    return True, ''

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
    """ Maneja el inicio de sesión de los usuarios."""
    if current_user.is_authenticated:
        return redirect(url_for('auth.base'))

    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            # Valida que los campos de usuario y contraseña no estén vacíos.
            if not username or not password:
                flash('Por favor, completa todos los campos', 'danger')
                return render_template('auth/index.html')
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
                        return render_template('auth/index.html')
                    else:
                        flash('Su cuenta se encuentra temporalmente bloqueada debido a demasiados intentos fallidos. Por favor, inténtelo de nuevo más tarde.', 'danger')
                        return render_template('auth/index.html')
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
                    # Incrementa el contador de intentos fallidos y actualiza la fecha.
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
            return render_template('auth/index.html')
            
    return render_template('auth/index.html')
    
@login_bp.route('/base')
@login_required # Decorador que asegura que solo los usuarios autenticados pueden acceder a esta ruta.
def base():
    """Ruta para la página principal de la aplicación, solo accesible para usuarios autenticados."""
    return render_template('base.html')
    
@login_bp.route('/logout')
@login_required
def logout():
    """Cierra la sesión del usuario actual."""
    try:
        logout_user() # Función de Flask-Login para cerrar la sesión.
        flash('Has cerrado sesión correctamente.', 'success')
        return redirect(url_for('auth.login'))
    except Exception as e:
        current_app.logger.error(f'Error al cerrar la sesión: {e}', exc_info=True)
        flash('Ocurrió un error inesperado al cerrar la sesión.\nPor favor, inténtelo de nuevo.', 'danger')
        return redirect(url_for('auth.base'))

@login_bp.route('/olvido_contrasena', methods=['GET'])
def olvido_contrasena():
    """Muestra la página de 'olvidó su contraseña' que redirige al administrador."""
    return render_template('auth/olvido_contrasena.html')


@login_bp.before_app_request
def redirect_if_password_change_required():
    # 1. Verificar si hay un usuario logueado
    if current_user.is_authenticated:
        
        # 2. Verificar si el cambio de contraseña es requerido
        if current_user.cambio_password_requerido:
            
            # 3. Obtener el nombre del endpoint al que el usuario intenta acceder
            endpoint = request.endpoint 
            
            if endpoint == 'static' or endpoint is None:
                return
            
            # Si el usuario intenta acceder a CUALQUIER COSA que no sea:
            #   - La página de cambio de contraseña ('auth.cambiar_contrasena')
            #   - La página de cierre de sesión ('auth.logout')
            # Lo redirigimos forzosamente a la página de cambio de contraseña.
            if (endpoint != 'auth.cambiar_contrasena' and 
                endpoint != 'auth.logout'):
                
                return redirect(url_for('auth.cambiar_contrasena'))

@login_bp.route('/admin/restablecer_contrasena', methods=['POST']) # ✅ Cambiar a solo POST
@login_required
def restablecer_contrasena_admin():
    """ Ruta para que un administrador restablezca la contraseña de otro usuario."""
    # Verifica si el usuario actual tiene el rol de 'admin'. Si no, lo redirige.
    if not current_user.rol.tipo_rol == 'admin':
        flash('No tiene permisos para acceder a esta página.', 'danger')
        return redirect(url_for('auth.base'))

    username = request.form.get('username')
    
    # Valida que se haya proporcionado un nombre de usuario.
    if not username:
        flash('No se ha proporcionado un nombre de usuario.', 'danger')
        # Redirige a una página segura si falta el dato.
        return redirect(url_for('empleado.listar_empleado'))
        
    usuario = Usuario.query.filter_by(username=username).first()

    # Obtiene el ID del empleado asociado para poder redirigir correctamente.
    empleado = Empleado.query.filter_by(Usuario_id_usuario=usuario.id_usuario).first()
    if not empleado:
        flash('Empleado no encontrado para el usuario especificado.', 'danger')
        return redirect(url_for('empleado.listar_empleado'))
    # Si no se encuentra el usuario, muestra un mensaje y redirige.
    if not usuario:
        flash(f'No se encontró ningún usuario con el nombre "{username}".', 'danger')
        return redirect(url_for('empleado.editar_empleado', id=empleado.id_empleado))

    try:
        # Genera una contraseña temporal segura y aleatoria.
        alphabet = string.ascii_letters + string.digits + string.punctuation
        temp_password = ''.join(secrets.choice(alphabet) for i in range(8))
        # Hashea la nueva contraseña y marca la cuenta para que el usuario la cambie.
        usuario.password = generate_password_hash(temp_password)
        usuario.cambio_password_requerido = True
        db.session.commit()
        # Muestra la contraseña temporal en un mensaje flash para que el administrador la comunique.
        flash(f'La contraseña para el usuario "{username}" ha sido restablecida. La nueva clave temporal es: {temp_password}', 'success')
        
    except Exception as e:
        current_app.logger.error(f'Error al restablecer la contraseña del usuario {username}: {e}', exc_info=True)
        flash('Ocurrió un error al restablecer la contraseña. Contacta a soporte.', 'danger')
    
    # Redirigir de vuelta a la página de edición del empleado
    return redirect(url_for('empleado.editar_empleado', id=empleado.id_empleado))

@login_bp.route('/cambiar_contrasena', methods=['GET', 'POST'])
@login_required
def cambiar_contrasena():
    """
    Permite a un usuario cambiar su contraseña temporal por una nueva.
    Esta ruta está protegida y solo se puede acceder si el usuario tiene el flag
    `cambio_password_requerido` en True.
    """
    # Redirige si el cambio de contraseña no es requerido.
    if not current_user.cambio_password_requerido:
        return redirect(url_for('auth.base'))
        
    if request.method == 'POST':
        nueva_contrasena = request.form.get('nueva_contrasena')
        confirmar_contrasena = request.form.get('confirmar_contrasena')
        # Valida que los campos no estén vacíos y que las contraseñas coincidan.
        if not nueva_contrasena or not confirmar_contrasena:
            flash('Por favor, completa todos los campos.', 'danger')
            return render_template('auth/cambiar_contrasena.html')

        # Aquí se realiza la nueva validación de complejidad
        es_valida, mensaje = validar_complejidad_password(nueva_contrasena)
        if not es_valida:
            flash(mensaje, 'danger')
            return render_template('auth/cambiar_contrasena.html')

        if nueva_contrasena != confirmar_contrasena:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('auth/cambiar_contrasena.html')

        try:
            # Hashea y guarda la nueva contraseña, y desactiva el flag de cambio requerido.
            current_user.password = generate_password_hash(nueva_contrasena)
            current_user.cambio_password_requerido = False
            db.session.commit()
            flash('Su contraseña ha sido actualizada exitosamente.', 'success')
            return redirect(url_for('auth.base'))

        except Exception as e:
            current_app.logger.error(f'Error al cambiar la contraseña del usuario {current_user.username}: {e}', exc_info=True)
            flash('Ocurrió un error al actualizar su contraseña. Intente de nuevo.', 'danger')

    return render_template('auth/cambiar_contrasena.html')
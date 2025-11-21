from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

""" Decorador de Roles """
def rol_requerido(rol):
    """
    Decorador principal que restringe el acceso a una ruta a usuarios con un rol específico.
    Si el usuario no está autenticado o no tiene el rol, se le redirige con un mensaje flash.
    """
    def decorator(f):
        # 'wraps' mantiene la información original de la función decorada (nombre, docstring, etc.).
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                # Si el usuario no está autenticado, lo redirige a la página de inicio de sesión.
                flash("Por favor, inicie sesión para acceder a esta página.", "info")
                return redirect(url_for('auth.login'))
            
            #  Verifica si el rol del usuario actual coincide con el rol requerido.
            if current_user.rol.tipo_rol != rol:
                # Si el rol no coincide, muestra un mensaje flash y redirige al inicio.
                flash("Acceso denegado. No tiene los permisos necesarios para esta acción.", "danger")
                return redirect(url_for('index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

""" Decorador de Permisos """
def permiso_requerido(permiso_nombre):
    """
    Decorador que verifica si el usuario autenticado tiene un permiso específico.
    Este decorador es más flexible que el de rol y permite un control de acceso granular.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                # Si no está autenticado, lo redirige al login
                flash("Por favor, inicie sesión para acceder a esta página.", "info")
                return redirect(url_for('auth.login'))
            
            # Verifica si el rol del usuario tiene el permiso requerido.
            # Se comprueba si el usuario tiene un rol asignado y si alguno de los permisos
            # de ese rol coincide con el 'permiso_nombre' que se busca.
            if not current_user.rol or not any(p.nombre == permiso_nombre for p in current_user.rol.permisos):
                flash("Acceso denegado. No tiene los permisos necesarios para esta acción.", "danger")
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Decorador 'Helper' para administradores ---
def admin_required(f):
    """
    Un decorador de conveniencia que utiliza 'rol_requerido'
    para proteger las rutas exclusivas de los administradores.
    """
    return rol_requerido('administrador')(f)
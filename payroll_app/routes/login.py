from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from payroll_app.models import Usuario, db
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta

login_bp = Blueprint('auth', __name__)

# ❗ Definir el límite de intentos y el tiempo de bloqueo
MAX_INTENTOS_FALLIDOS = 5
TIEMPO_BLOQUEO_MINUTOS = 15


@login_bp.route('/')
def home():
    """Redirige la ruta principal a la página de login."""
    if current_user.is_authenticated:
        return redirect(url_for('auth.base'))
    return redirect(url_for('auth.login'))

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.base'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
    
        if not username or not password:
            flash('Por favor, completa todos los campos', 'danger')
            return render_template('index.html')
        
        usuario = Usuario.query.filter_by(username=username).first()
        
        if usuario:
            # ❗ Lógica de desbloqueo temporal: si la cuenta está inactiva y ha pasado el tiempo de bloqueo
            if not usuario.estado_usuario:
                tiempo_transcurrido = datetime.utcnow() - usuario.fecha_ultimo_intento
                if tiempo_transcurrido.total_seconds() >= TIEMPO_BLOQUEO_MINUTOS * 60:
                    usuario.estado_usuario = True
                    usuario.intentos_fallidos = 0
                    db.session.commit()
                    flash('Su cuenta ha sido desbloqueada. Por favor, intente iniciar sesión de nuevo.', 'success')
                    return render_template('index.html')
                else:
                    flash('Su cuenta se encuentra temporalmente bloqueada debido a demasiados intentos fallidos. Por favor, inténtelo de nuevo más tarde.', 'danger')
                    return render_template('index.html')
                    
            if check_password_hash(usuario.password, password):
                # ❗ Inicio de sesión exitoso: restablecer intentos
                usuario.intentos_fallidos = 0
                usuario.fecha_ultimo_intento = datetime.utcnow()
                db.session.commit()
                login_user(usuario) 
                flash('Inicio de sesión exitoso.', 'success')
                return redirect(url_for('auth.base'))
            else:
                # ❗ Intento de sesión fallido
                usuario.intentos_fallidos += 1
                usuario.fecha_ultimo_intento = datetime.utcnow()
                db.session.commit()
                
                if usuario.intentos_fallidos >= MAX_INTENTOS_FALLIDOS:
                    usuario.estado_usuario = False
                    db.session.commit()
                    flash(f'Se ha excedido el número de intentos. Su cuenta ha sido bloqueada por {TIEMPO_BLOQUEO_MINUTOS} minutos.', 'danger')
                else:
                    flash('Nombre de usuario o contraseña incorrecta. Por favor, inténtelo de nuevo.', 'danger')
        else:
            flash('Nombre de usuario o contraseña incorrecta. Por favor, inténtelo de nuevo.', 'danger')
            
    return render_template('index.html')

@login_bp.route('/base')
@login_required
def base():
    # Flask-Login pasa la información del usuario a la plantilla automáticamente
    return render_template('base.html')
    
@login_bp.route('/logout')
def logout():
    logout_user()
    flash('Has cerrado sesión correctamente.', 'success')
    return redirect(url_for('auth.login'))

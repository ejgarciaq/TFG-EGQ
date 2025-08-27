from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from payroll_app.models import Usuario
from flask_login import login_user, logout_user, login_required, current_user

login_bp = Blueprint('auth', __name__)

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
        
        if usuario and check_password_hash(usuario.password, password):
            login_user(usuario) 
            flash('Inicio de sesión exitoso.', 'success')
            return redirect(url_for('auth.base'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')
            
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

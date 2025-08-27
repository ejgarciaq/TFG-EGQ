from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from payroll_app.models import Usuario

login_bp = Blueprint('auth', __name__)

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
  
        #Print(f"Username: {username}, Password: {password}")  # Depuración
        # Verificar si los campos están vacíos
        if not username or not password:
            flash('Por favor, completa todos los campos', 'danger')
            return render_template('index.html')
        
        # Buscar el usuario en la base de datos
        usuario = Usuario.query.filter_by(username=username).first()
        #print(f"Usuario encontrado: {usuario}")  # Depuración

        # Verificar si el usuario existe y la contraseña es correcta
        if usuario and check_password_hash(usuario.password, password): 
            session['username'] = username # Almacena el nombre de usuario en la sesión
            # Redirigir al panel si las credenciales son correctas
            flash('Inicio de sesión exitoso.', 'success')
            #print("Redirigiendo a /auth/base")  # Depuración
            return redirect(url_for('auth.base'))  # Redirige a la ruta 'base'
        else:
            # Mostrar mensaje de error si las credenciales son incorrectas
            flash('Usuario o contraseña incorrectos.', 'danger')
            #print("Credenciales incorrectas")  # Depuración
    return render_template('index.html')
    


@login_bp.route('/base')
def base():
    if 'username' in session:  # Verifica si el nombre de usuario está en la sesión
        username = session['username']
        return render_template('base.html', username=username)  # Pasa el nombre de usuario a la plantilla
    else:
        return redirect(url_for('login'))  # Redirige al inicio de sesión si no hay sesión activa
    
@login_bp.route('/logout')
def logout():
    session.pop('username', None)  # Elimina el nombre de usuario de la sesión
    flash('Has cerrado sesión correctamente.', 'success')
    return redirect(url_for('auth.login'))  # Redirige a la página de inicio de sesión
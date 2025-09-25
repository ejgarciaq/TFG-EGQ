import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, redirect, url_for
from flask_mail import Mail
from payroll_app.config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# --- Inicialización de extensiones fuera de la fábrica de aplicaciones ---
# Estas instancias se inicializan aquí para que puedan ser importadas
# en otros módulos (como routes.py o models.py) sin crear una dependencia circular.

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

# --- Función de la fábrica de aplicaciones ---
# La 'fábrica de aplicaciones' (application factory) es un patrón recomendado en Flask
# que permite crear la aplicación de manera flexible, útil para pruebas y múltiples entornos.

def create_app():
    # Crea la instancia principal de la aplicación Flask
    app = Flask(__name__)
    # Carga la configuración desde el objeto Config, que contiene las variables de entorno
    app.config.from_object(Config)
    # Inicializa las extensiones con la instancia de la aplicación
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail = Mail(app)

    # --- Configuración de Flask-Login ---
    # Define la vista de inicio de sesión que Flask-Login debe redirigir a los usuarios
    # no autenticados.
    login_manager.login_view = 'auth.login'
    # Personaliza los mensajes y la categoría de los mensajes flash
    login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
    login_manager.login_message_category = 'warning'

    # --- Configuración del Logging (registro de eventos) ---
    # Esta sección configura la escritura de logs en un archivo para la aplicación
    # en un entorno de producción (cuando app.debug es False).
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        # RotatingFileHandler: Mueve los logs viejos a un nuevo archivo cuando el actual
        # alcanza el tamaño máximo (10 KB) y mantiene un máximo de 10 archivos de respaldo.
        file_handler = RotatingFileHandler('logs/payroll_app.log', maxBytes=10240, backupCount=10)
        # Define el formato de cada línea del log
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

    # --- Función de carga de usuario para Flask-Login ---
    # Esta función es crucial para que Flask-Login sepa cómo cargar un usuario
    # a partir de su ID de sesión.
    from .models import Usuario
    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))
    
    # --- Importación y registro de Blueprints ---
    # Los 'Blueprints' organizan el código en módulos para que la aplicación
    # sea más manejable y escalable. Cada Blueprint representa un área de la aplicación.
    from .routes.login import login_bp
    from .routes.empleado import empleado_bp
    from .routes.rol import rol_bp
    from .routes.puesto import puesto_bp
    from .routes.registro_asistencia import registro_asistencia_bp
    from .routes.feriado import feriado_bp
    from .routes.accion_personal import accion_personal_bp
    from .routes.reportes import reportes_bp
    from .routes.aguinaldo import aguinaldo_bp

    app.register_blueprint(login_bp, url_prefix='/auth')
    app.register_blueprint(empleado_bp, url_prefix='/auth/empleados')
    app.register_blueprint(rol_bp, url_prefix='/auth/roles')
    app.register_blueprint(puesto_bp, url_prefix='/auth/puestos')
    app.register_blueprint(registro_asistencia_bp, url_prefix='/auth/registro_asistencia')
    app.register_blueprint(feriado_bp, url_prefix='/auth/feriados')
    app.register_blueprint(accion_personal_bp, url_prefix='/auth/accion_personal')
    app.register_blueprint(reportes_bp, url_prefix='/auth/reportes/')
    app.register_blueprint(aguinaldo_bp, url_prefix='/auth/aguinaldo')

    # --- Definición de la ruta principal ---
    # La ruta raíz de la aplicación (/) redirige al usuario a la página de login.
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # Devuelve la instancia de la aplicación configurada
    return app
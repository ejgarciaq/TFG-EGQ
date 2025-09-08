import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, redirect, url_for
from payroll_app.config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['SECRET_KEY'] = 'f9ddc90157c588ce310b85c62fe82b7e76c94a87'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Configuración de Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
    login_manager.login_message_category = 'warning'

    # ❗ Configuración del logging para la aplicación principal
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/payroll_app.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

    from .models import Usuario
    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))
    
    # Importar y registrar blueprints
    from .routes.login import login_bp
    from .routes.empleado import empleado_bp
    from .routes.rol import rol_bp
    from .routes.puesto import puesto_bp
    from .routes.registro_asistencia import registro_asistencia_bp
    from .routes.feriado import feriado_bp
    from .routes.accion_personal import accion_personal_bp

    app.register_blueprint(login_bp, url_prefix='/auth')
    app.register_blueprint(empleado_bp, url_prefix='/auth/empleados')
    app.register_blueprint(rol_bp, url_prefix='/auth/roles')
    app.register_blueprint(puesto_bp, url_prefix='/auth/puestos')
    app.register_blueprint(registro_asistencia_bp, url_prefix='/auth/registro_asistencia')
    app.register_blueprint(feriado_bp, url_prefix='/auth/feriados')
    app.register_blueprint(accion_personal_bp, url_prefix='/auth/accion_personal')

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    return app
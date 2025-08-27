from flask import Flask
from payroll_app.config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()  # Inicializa la instancia de SQLAlchemy

migrate = Migrate()  # Inicializa la instancia de Flask-Migrate


def create_app():
    app = Flask(__name__) # Crea una instancia de la aplicación Flask
    app.config.from_object(Config)  # Carga la configuración desde el objeto Config
    # Importate: Agrega un secreto para que la sesión funcione
    app.config['SECRET_KEY'] = 'f9ddc90157c588ce310b85c62fe82b7e76c94a87'  # Cambia esto por una clave secreta segura

    db.init_app(app)  # Inicializa la instancia de SQLAlchemy con la aplicación
    migrate.init_app(app, db)  # Inicializa Migrate con la app y la db

    # Agrega el proceso de contexto de la aplicación
    @app.context_processor
    def inject_user():
        from flask import session
        username = session.get('username')
        return dict(username=username)

    # Importar los modelos para que SQLAlchemy los reconozca
    from . import models
    from .routes.login import login_bp
    from .routes.empleado import empleado_bp
    from .routes.rol import rol_bp
    from .routes.puesto import puesto_bp
    
    # Registra el blueprint de login
    app.register_blueprint(login_bp, url_prefix='/auth')  # Registra el blueprint de rutas
    app.register_blueprint(empleado_bp, url_prefix='/auth/empleados')  # Registra el blueprint de rutas
    app.register_blueprint(rol_bp, url_prefix='/auth/roles')  # Registra el blueprint de rutas
    app.register_blueprint(puesto_bp, url_prefix='/auth/puestos')  # Registra el blueprint de rutas

    return app  # Devuelve la instancia de la aplicación Flask

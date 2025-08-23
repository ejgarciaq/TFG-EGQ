from flask import Flask
from payroll_app.config import Config
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()  # Inicializa la instancia de SQLAlchemy

def create_app():
    app = Flask(__name__) # Crea una instancia de la aplicación Flask
    app.config.from_object(Config)  # Carga la configuración desde el objeto Config
    db.init_app(app)  # Inicializa la instancia de SQLAlchemy con la aplicación

    # Importar los modelos para que SQLAlchemy los reconozca
    from . import models
    from .routes.login import login_bp
    from .routes.empleado import empleado_bp
    
    # Registra el blueprint de login
    app.register_blueprint(login_bp, url_prefix='/auth')  # Registra el blueprint de rutas
    app.register_blueprint(empleado_bp, url_prefix='/empleados')  # Registra el blueprint de rutas

    return app  # Devuelve la instancia de la aplicación Flask

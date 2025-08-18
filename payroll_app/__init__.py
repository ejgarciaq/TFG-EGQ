from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from payroll_app.config import Config
from .models import db  # Importa la instancia de SQLAlchemy desde models.py
from payroll_app.routes.login import login_bp   # Importa el blueprint de login

db = SQLAlchemy() # Inicializa la instancia de SQLAlchemy

def create_app():
    app = Flask(__name__) # Crea una instancia de la aplicación Flask
    app.config.from_object(Config)  # Carga la configuración desde el objeto Config
    db.init_app(app)  # Inicializa la instancia de SQLAlchemy con la aplicación

    # Registra el blueprint de login
    app.register_blueprint(login_bp, url_prefix='/auth')  # Registra el blueprint de rutas
    return app  # Devuelve la instancia de la aplicación Flask

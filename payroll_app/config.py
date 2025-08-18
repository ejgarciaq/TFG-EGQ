from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Config:
    """
    Configuration class for the payroll application.
    """
    SECRET_KEY = '9c17f91a8d1b48a29d1f52d7c8fb30e9'  # Clave secreta para proteger sesiones y cookies
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:2WpIC2frx7AcNZJ.@localhost/rhcontrol'  # URI de la base de datos MySQL
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Desactiva el seguimiento de modificaciones para evitar advertencias
    DEBUG = True  # Modo de depuración activado
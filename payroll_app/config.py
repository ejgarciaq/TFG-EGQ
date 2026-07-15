import os
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def get_database_uri():
    """Return the selected database URI from environment variables.

    Use DB_MODE or APP_DB_MODE to choose between a test connection and the
    default/production connection.
    """
    mode = os.getenv('DB_MODE', os.getenv('APP_DB_MODE', 'default')).strip().lower()

    if mode == 'test':
        return (
            os.getenv('TEST_DATABASE_URL')
            or os.getenv('TEST_SQLALCHEMY_DATABASE_URI')
            or 'mysql+pymysql://root:2WpIC2frx7AcNZJ.@localhost/rhcontrol'
        )

    return (
        os.getenv('DATABASE_URL')
        or os.getenv('SQLALCHEMY_DATABASE_URI')
        or 'mysql+pymysql://root:cayeYxFTpqyBizlNLpICucaSvBTTGriB@tokaido.proxy.rlwy.net:54879/rhcontrol'
    )

class Config:
    """
    Clase de configuración para la aplicación de nómina.
    
    Esta clase agrupa todas las variables de configuración de la aplicación,
    facilitando su gestión y permitiendo la separación de la lógica del código.
    """

    # SECRET_KEY es una clave criptográfica que se utiliza para firmar sesiones,
    # cookies y otros datos sensibles. Es crucial para la seguridad de la aplicación
    # y debe ser un valor único y difícil de adivinar en un entorno de producción.
    SECRET_KEY = os.getenv('SECRET_KEY', 'f9ddc90157c588ce310b85c62fe82b7e76c94a87')

    # SQLALCHEMY_DATABASE_URI define la cadena de conexión a la base de datos.
    # El formato es: 'dialect+driver://usuario:contraseña@host/nombre_db'
    # Se puede elegir entre una conexión de prueba y una de desarrollo/producción
    # mediante la variable DB_MODE o APP_DB_MODE.
    DB_MODE = os.getenv('DB_MODE', os.getenv('APP_DB_MODE', 'default')).strip().lower()
    SQLALCHEMY_DATABASE_URI = get_database_uri()

    # SQLALCHEMY_TRACK_MODIFICATIONS es una configuración opcional que, si se
    # activa, genera eventos de señal para cada cambio en los objetos de la base de datos.
    # Se desactiva para mejorar el rendimiento y evitar advertencias innecesarias,
    # ya que la mayoría de los desarrolladores no la necesitan.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # DEBUG activa el modo de depuración de Flask. Cuando está en True,
    # el servidor se reinicia automáticamente al detectar cambios en el código
    # y proporciona un depurador interactivo en el navegador para los errores,
    # lo cual es muy útil durante el desarrollo.
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() in ('1', 'true', 'yes', 'on')

    # Configuración del servidor de correo
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() in ('1', 'true', 'yes', 'on')
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', 'fundacionbanderablanca9@gmail.com')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', 'vcox lmdc burq jlxm')
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
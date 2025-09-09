from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Config:
    """
    Clase de configuración para la aplicación de nómina.
    
    Esta clase agrupa todas las variables de configuración de la aplicación,
    facilitando su gestión y permitiendo la separación de la lógica del código.
    """

    # SECRET_KEY es una clave criptográfica que se utiliza para firmar sesiones,
    # cookies y otros datos sensibles. Es crucial para la seguridad de la aplicación
    # y debe ser un valor único y difícil de adivinar en un entorno de producción.
    SECRET_KEY = 'f9ddc90157c588ce310b85c62fe82b7e76c94a87'
    # SQLALCHEMY_DATABASE_URI define la cadena de conexión a la base de datos.
    # El formato es: 'dialect+driver://usuario:contraseña@host/nombre_db'
    # En este caso, se conecta a una base de datos MySQL llamada 'rhcontrol'
    # en el servidor local (localhost).
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:2WpIC2frx7AcNZJ.@localhost/rhcontrol'
    # SQLALCHEMY_TRACK_MODIFICATIONS es una configuración opcional que, si se
    # activa, genera eventos de señal para cada cambio en los objetos de la base de datos.
    # Se desactiva para mejorar el rendimiento y evitar advertencias innecesarias,
    # ya que la mayoría de los desarrolladores no la necesitan.
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # DEBUG activa el modo de depuración de Flask. Cuando está en True,
    # el servidor se reinicia automáticamente al detectar cambios en el código
    # y proporciona un depurador interactivo en el navegador para los errores,
    # lo cual es muy útil durante el desarrollo.
    DEBUG = True  # Modo de depuración activado
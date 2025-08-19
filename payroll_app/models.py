from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()  # Inicializa la instancia de SQLAlchemy

## Gestion Administrativa de la base de datos ##

class Rol(db.Model):
    """
    Modelo de Rol para la aplicación de nómina.
    Representa un rol con un nombre único y una descripción.
    """
    id_rol = db.Column(db.Integer, primary_key=True)  # ID único del rol
    tipo_rol = db.Column(db.String(100), unique=True, nullable=False)  # Nombre del rol único

    # Relación inversa: lista de usuarios asociados a este rol
    usuarios = db.relationship('Usuario', back_populates='rol')
    
    def __repr__(self):
        return f'<Rol {self.tipo_rol}>'  # Representación del objeto Rol

class Usuario(db.Model):
    """
    Modelo de Usuario para la aplicación de nómina.
    Representa a un usuario con nombre de usuario y contraseña.
    """
    id_usuario = db.Column(db.Integer, primary_key=True)  # ID único del usuario
    username = db.Column(db.String(50), unique=True, nullable=False)  # Nombre de usuario único
    password = db.Column(db.String(255), nullable=False)  # Contraseña del usuario
    estado_usuario = db.Column(db.Boolean, nullable=False)  # Estado del usuario (activo/inactivo)

    # Clave foránea para la relación con el modelo Rol
    Rol_id_rol = db.Column(db.Integer, db.ForeignKey('rol.id_rol'), nullable=False)
    # Relación con el modelo Rol
    rol = db.relationship('Rol', back_populates='usuarios')

    def __repr__(self):
        return f'<Usuario {self.username}>'  # Representación del objeto Usuario
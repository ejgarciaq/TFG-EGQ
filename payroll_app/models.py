from payroll_app import db
from datetime import date

## Gestión Administrativa de la base de datos ##

class Rol(db.Model):
    """
    Modelo de Rol para la aplicación de nómina.
    Representa un rol con un nombre único y una descripción.
    """
    __tablename__ = 'rol'  # Nombre de la tabla en la base de datos
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
    __tablename__ = 'usuario'  # Nombre de la tabla en la base de datos
    id_usuario = db.Column(db.Integer, primary_key=True)  # ID único del usuario
    username = db.Column(db.String(50), unique=True, nullable=False)  # Nombre de usuario único
    password = db.Column(db.String(255), nullable=False)  # Contraseña del usuario
    estado_usuario = db.Column(db.Boolean, nullable=False)  # Estado del usuario (activo/inactivo)
    Rol_id_rol = db.Column(db.Integer, db.ForeignKey('rol.id_rol'), nullable=False)  # Clave foránea para la relación con el modelo Rol

    rol = db.relationship('Rol', back_populates='usuarios')  # Relación con el modelo Rol
    # Relación inversa: empleado asociado a este usuario
    empleado = db.relationship('Empleado', back_populates='usuario', uselist=False)

    def __repr__(self):
        return f'<Usuario {self.username}>'  # Representación del objeto Usuario
    
class Puesto(db.Model):
    """
    Modelo de Puesto para la aplicación de nómina.
    Representa un puesto con un nombre único y una descripción.
    """
    __tablename__ = 'puesto'  # Nombre de la tabla en la base de datos
    id_puesto = db.Column(db.Integer, primary_key=True)  # ID único del puesto
    tipo_puesto = db.Column(db.String(100), unique=True, nullable=False)  # Nombre del puesto único
    # Relación inversa: lista de empleados asociados a este puesto
    empleados = db.relationship('Empleado', back_populates='puesto')

    def __repr__(self):
        # Corregido: 'nombre_puesto' a 'tipo_puesto'
        return f'<Puesto {self.tipo_puesto}>'
    
class Empleado(db.Model):
    """
    Modelo de Empleado para la aplicación de nómina.
    Representa a un empleado con información personal y laboral.
    """
    __tablename__ = 'empleado'  # Nombre de la tabla en la base de datos
    id_empleado = db.Column(db.Integer, primary_key=True)  # ID único del empleado
    nombre = db.Column(db.String(100), nullable=False)  # Nombre del empleado
    apellido_primero = db.Column(db.String(100), nullable=False)  # Apellido del empleado
    apellido_segundo = db.Column(db.String(100), nullable=True)  # Segundo apellido del empleado
    cedula = db.Column(db.String(20), unique=True, nullable=False)  # Cédula del empleado
    correo = db.Column(db.String(100), unique=True, nullable=False)  # Correo electrónico del empleado
    telefono = db.Column(db.String(15), nullable=False)  # Teléfono del empleado
    fecha_ingreso = db.Column(db.Date, nullable=False)  # Fecha de ingreso del empleado
    salario_base = db.Column(db.Float, nullable=False)  # Salario base del empleado
    fecha_salida = db.Column(db.Date, nullable=True)  # Fecha de salida del empleado (opcional)
    estado_empleado = db.Column(db.Boolean, nullable=False)  # Estado del empleado (activo/inactivo)

    # Claves foráneas
    Puesto_id_puesto = db.Column(db.Integer, db.ForeignKey('puesto.id_puesto'), nullable=False)
    Usuario_id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'), nullable=False)

    # Relaciones
    usuario = db.relationship('Usuario', back_populates='empleado')
    puesto = db.relationship('Puesto', back_populates='empleados')

    def __repr__(self):
        return f'<Empleado {self.nombre} {self.apellido_primero}>'
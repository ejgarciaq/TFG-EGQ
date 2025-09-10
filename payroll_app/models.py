from datetime import datetime
from payroll_app import db
from flask_login import UserMixin

# Gestión Administrativa de la base de datos
# Este archivo define la estructura de las tablas de la base de datos
# a través de los modelos de SQLAlchemy, facilitando la interacción con la misma.

# --- Tabla de unión para la relación muchos a muchos entre Rol y Permiso ---
# Esta tabla es necesaria para que un Rol pueda tener múltiples Permisos, y un
# Permiso pueda estar asociado a múltiples Roles, sin repetir datos.
rol_permiso = db.Table('rol_permiso',
    db.Column('id_rol', db.Integer, db.ForeignKey('rol.id_rol'), primary_key=True),
    db.Column('id_permiso', db.Integer, db.ForeignKey('permiso.id_permiso'), primary_key=True)
)

# --- Permisos ---
class Permiso(db.Model):
    """
    Modelo para la tabla 'permiso'.
    Almacena los permisos granulares del sistema (ej. 'ver_nomina', 'editar_empleado').
    """
    __tablename__ = 'permiso'
    id_permiso = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.String(255))
    
    def __repr__(self):
        return f'<Permiso {self.nombre}>'

# --- Roles ---
class Rol(db.Model):
    """
    Modelo para la tabla 'rol'.
    Almacena los roles de usuario (ej. 'Administrador', 'Empleado').
    Ahora incluye una relación con los permisos a través de la tabla de unión.
    """
    __tablename__ = 'rol'
    id_rol = db.Column(db.Integer, primary_key=True)
    tipo_rol = db.Column(db.String(100), unique=True, nullable=False)
    descripcion_rol = db.Column(db.String(255), nullable=True)
    usuarios = db.relationship('Usuario', back_populates='rol')
    
    # Relación muchos a muchos con el modelo Permiso.
    # 'secondary' indica la tabla de unión que se usará.
    # 'lazy' define cómo se cargan los datos. 'subquery' carga los permisos en una sola consulta.
    # 'backref' crea una relación inversa en el modelo Permiso.
    permisos = db.relationship('Permiso', secondary=rol_permiso, lazy='subquery',
                               backref=db.backref('roles', lazy=True))
    
    def __repr__(self):
        return f'<Rol {self.tipo_rol}>'
    
# --- Usuarios ---
class Usuario(db.Model, UserMixin):
    """
    Modelo para la tabla 'usuario'.
    Almacena la información de inicio de sesión de los usuarios.
    'UserMixin' añade propiedades y métodos para Flask-Login.
    """
    __tablename__ = 'usuario'
    id_usuario = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    estado_usuario = db.Column(db.Boolean, nullable=False)
    # Llave foránea que relaciona un Usuario con un Rol.
    Rol_id_rol = db.Column(db.Integer, db.ForeignKey('rol.id_rol'), nullable=False)
    
    # Relaciones bidireccionales con Rol y Empleado para facilitar la navegación.
    rol = db.relationship('Rol', back_populates='usuarios')
    empleado = db.relationship('Empleado', back_populates='usuario', uselist=False)
    
    # Campos de seguridad para el control de acceso
    intentos_fallidos = db.Column(db.Integer, default=0, nullable=False)
    fecha_ultimo_intento = db.Column(db.DateTime, nullable=True)
    cambio_password_requerido = db.Column(db.Boolean, default=False, nullable=False)

    def get_id(self):
        """Método requerido por Flask-Login para obtener el ID del usuario."""
        return str(self.id_usuario)

    def __repr__(self):
        return f'<Usuario {self.username}>'
    
# --- Puesto ---
class Puesto(db.Model):
    """
    Modelo para la tabla 'puesto'.
    Almacena los diferentes puestos de trabajo en la empresa.
    """
    __tablename__ = 'puesto'
    id_puesto = db.Column(db.Integer, primary_key=True)
    tipo_puesto = db.Column(db.String(100), unique=True, nullable=False)
    empleados = db.relationship('Empleado', back_populates='puesto')

    def __repr__(self):
        return f'<Puesto {self.tipo_puesto}>'
    
# --- Empleados ---
class Empleado(db.Model):
    """
    Modelo para la tabla 'empleado'.
    Almacena la información personal y laboral de cada empleado.
    """
    __tablename__ = 'empleado'
    id_empleado = db.Column(db.Integer, primary_key=True)
    
    # Datos personales
    nombre = db.Column(db.String(100), nullable=False)
    apellido_primero = db.Column(db.String(100), nullable=False)
    apellido_segundo = db.Column(db.String(100), nullable=True)
    cedula = db.Column(db.String(20), unique=True, nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    telefono = db.Column(db.String(15), nullable=False)
    
    # Datos laborales
    fecha_ingreso = db.Column(db.Date, nullable=False)
    salario_base = db.Column(db.Float, nullable=False)
    fecha_salida = db.Column(db.Date, nullable=True)
    estado_empleado = db.Column(db.Boolean, nullable=False)
    
    # Claves foráneas que conectan Empleado a otras tablas.
    Puesto_id_puesto = db.Column(db.Integer, db.ForeignKey('puesto.id_puesto'), nullable=False)
    TipoNomina_id_tipo_nomina = db.Column(db.Integer, db.ForeignKey('tipo_nomina.id_tipo_nomina'), nullable=False)
    Usuario_id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'), unique=True, nullable=False)

    # Control de vacaciones
    vacaciones_disponibles = db.Column(db.Integer, default=0, nullable=False)
    
    # Relaciones que facilitan la consulta de datos relacionados.
    usuario = db.relationship('Usuario', back_populates='empleado')
    puesto = db.relationship('Puesto', back_populates='empleados')
    nominas = db.relationship('Nomina', back_populates='empleado')
    registros_asistencia = db.relationship('RegistroAsistencia', backref='empleado', lazy=True)
    tipo_nomina_relacion = db.relationship('TipoNomina', back_populates='empleados_relacionados', lazy=True)
    
    @property
    def nombre_completo(self):
        """Devuelve el nombre y los apellidos completos del empleado."""
        if self.apellido_segundo:
            return f"{self.nombre} {self.apellido_primero} {self.apellido_segundo}"
        return f"{self.nombre} {self.apellido_primero}"

    def __repr__(self):
        return f'<Empleado {self.nombre} {self.apellido_primero}>'
    
# --- Feriados ---
class Feriado(db.Model):
    """
    Modelo para la tabla 'feriado'.
    Almacena los días feriados o festivos.
    """
    __tablename__ = 'feriado'
    id_feriado = db.Column(db.Integer, primary_key=True)
    fecha_feriado = db.Column(db.Date, unique=True, nullable=False)
    descripcion_feriado = db.Column(db.String(255), nullable=True)
    pago_obligatorio = db.Column(db.Boolean, nullable=False, default=False)
    registros_asistencia = db.relationship('RegistroAsistencia', back_populates='feriado_relacion')

    def __repr__(self):
        return f'<Feriado {self.fecha_feriado}>'

# --- Tipo de nomina ---
class TipoNomina(db.Model):
    """
    Modelo para la tabla 'tipo_nomina'.
    Clasifica los tipos de nómina (ej. quincenal, mensual).
    """
    __tablename__ = 'tipo_nomina'
    id_tipo_nomina = db.Column(db.Integer, primary_key=True)
    nombre_tipo = db.Column(db.String(50), nullable=False)
    nominas_relacionadas = db.relationship('Nomina', back_populates='tipo_nomina_relacion', lazy=True)
    empleados_relacionados = db.relationship('Empleado', back_populates='tipo_nomina_relacion', lazy=True)

    def __repr__(self):
        return f'<TipoNomina {self.nombre_tipo}>'

# --- Nomina ---
class Nomina(db.Model):
    """
    Modelo para la tabla 'nomina'.
    Almacena los registros de cálculo de nómina para un empleado en un periodo.
    """
    __tablename__ = 'nomina'
    id_nomina = db.Column(db.Integer, primary_key=True)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    salario_bruto = db.Column(db.Float, nullable=False)
    salario_neto = db.Column(db.Float, nullable=False)
    deducciones = db.Column(db.Float, nullable=False, default=0.0)
    pago_obligatorio = db.Column(db.Boolean, nullable=False, default=False)
    fecha_creacion = db.Column(db.DateTime, nullable=False)
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    TipoNomina_id_tipo_nomina = db.Column(db.Integer, db.ForeignKey('tipo_nomina.id_tipo_nomina'), nullable=False)
    empleado = db.relationship('Empleado', back_populates='nominas')
    registros_asistencia = db.relationship('RegistroAsistencia', back_populates='nomina_relacion')
    tipo_nomina_relacion = db.relationship('TipoNomina', back_populates='nominas_relacionadas', lazy=True)

    def __repr__(self):
        return f'<Nomina {self.id_nomina} del Empleado {self.Empleado_id_empleado}>'
    
# --- Registro de Asistencia ---
class RegistroAsistencia(db.Model):
    """
    Modelo para la tabla 'registro_asistencia'.
    Almacena los registros diarios de entrada y salida de los empleados.
    """
    __tablename__ = 'registro_asistencia'
    id_registro_asistencia = db.Column(db.Integer, primary_key=True)
    fecha_registro = db.Column(db.Date, nullable=False)
    hora_entrada = db.Column(db.Time, nullable=False)
    hora_salida = db.Column(db.Time, nullable=True)
    total_horas = db.Column(db.Float, nullable=True)
    monto_pago = db.Column(db.Float, nullable=True)
    hora_nominal = db.Column(db.Float, nullable=True)
    hora_extra = db.Column(db.Float, nullable=True)
    hora_feriado = db.Column(db.Float, nullable=True)
    aprobacion_registro = db.Column(db.Boolean, nullable=False, default=False)
    Nomina_id_nomina = db.Column(db.Integer, db.ForeignKey('nomina.id_nomina'), nullable=True)
    Feriado_id_feriado = db.Column(db.Integer, db.ForeignKey('feriado.id_feriado'), nullable=True)
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    feriado_relacion = db.relationship('Feriado', back_populates='registros_asistencia')
    nomina_relacion = db.relationship('Nomina', back_populates='registros_asistencia')

    def __repr__(self):
        return f'<RegistroAsistencia {self.id_registro_asistencia}>'
    
# --- Aguinaldo ---
class Aguinaldo(db.Model):
    """
    Modelo para la tabla que almacena el cálculo y el registro del aguinaldo.
    """
    __tablename__ = 'aguinaldo'
    id_aguinaldo = db.Column(db.Integer, primary_key=True)
    fecha_pago = db.Column(db.Date, nullable=False)
    monto = db.Column(db.Float, nullable=False)
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    empleado_relacion = db.relationship('Empleado', backref='aguinaldos', lazy=True)
    
    def __repr__(self):
        return f'<Aguinaldo {self.id_aguinaldo} para Empleado {self.Empleado_id_empleado}>' 
        
# --- Tipo de Acción de Personal ---
class Tipo_AP(db.Model):
    """
    Modelo para la tabla que clasifica los tipos de acción de personal.
    """
    __tablename__ = 'tipo_ap'
    id_tipo_ap = db.Column(db.Integer, primary_key=True)
    nombre_tipo = db.Column(db.String(100), unique=True, nullable=False)
    descripcion_tipo = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f'<Tipo_AP {self.nombre_tipo}>'
    
# --- Acción de Personal ---
class Accion_Personal(db.Model):
    """
    Modelo para la tabla que registra las acciones de personal.
    Incluye los campos necesarios para solicitudes de vacaciones, incapacidades, etc.
    """
    __tablename__ = 'accion_personal'
    
    id_accion = db.Column(db.Integer, primary_key=True)
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    Tipo_Ap_id_tipo_ap = db.Column(db.Integer, db.ForeignKey('tipo_ap.id_tipo_ap'), nullable=False)
    fecha_accion = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    detalles = db.Column(db.Text, nullable=True)
    cantidad_dia = db.Column(db.Integer, nullable=True)
    fecha_inicio = db.Column(db.Date, nullable=True)
    fecha_fin = db.Column(db.Date, nullable=True)
    estado_ap = db.Column(db.Integer, nullable=False, default=1)
    id_aprobador = db.Column(db.Integer, nullable=True)
    fecha_aprobacion = db.Column(db.DateTime, nullable=True)
    documento_adjunto = db.Column(db.Text, nullable=True)
    
    # Relaciones de SQLAlchemy
    empleado = db.relationship('Empleado', backref='acciones_personales', lazy=True)
    tipo_ap = db.relationship('Tipo_AP', backref='acciones_personales', lazy=True)

    def __repr__(self):
        return f'<Accion_Personal {self.id_accion} Tipo: {self.Tipo_Ap_id_tipo_ap}>'
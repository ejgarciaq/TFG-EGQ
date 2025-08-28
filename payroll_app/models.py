from payroll_app import db
from flask_login import UserMixin

## Gestión Administrativa de la base de datos ##

class Rol(db.Model):
    __tablename__ = 'rol'
    id_rol = db.Column(db.Integer, primary_key=True)
    tipo_rol = db.Column(db.String(100), unique=True, nullable=False)
    descripcion_rol = db.Column(db.String(255), nullable=True)
    usuarios = db.relationship('Usuario', back_populates='rol')
    
    def __repr__(self):
        return f'<Rol {self.tipo_rol}>'

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuario'
    id_usuario = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    estado_usuario = db.Column(db.Boolean, nullable=False)
    Rol_id_rol = db.Column(db.Integer, db.ForeignKey('rol.id_rol'), nullable=False)
    rol = db.relationship('Rol', back_populates='usuarios')
    empleado = db.relationship('Empleado', back_populates='usuario', uselist=False)

    def get_id(self):
        return str(self.id_usuario)

    def __repr__(self):
        return f'<Usuario {self.username}>'
    
class Puesto(db.Model):
    __tablename__ = 'puesto'
    id_puesto = db.Column(db.Integer, primary_key=True)
    tipo_puesto = db.Column(db.String(100), unique=True, nullable=False)
    empleados = db.relationship('Empleado', back_populates='puesto')

    def __repr__(self):
        return f'<Puesto {self.tipo_puesto}>'
    
class Empleado(db.Model):
    __tablename__ = 'empleado'
    id_empleado = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido_primero = db.Column(db.String(100), nullable=False)
    apellido_segundo = db.Column(db.String(100), nullable=True)
    cedula = db.Column(db.String(20), unique=True, nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    telefono = db.Column(db.String(15), nullable=False)
    fecha_ingreso = db.Column(db.Date, nullable=False)
    salario_base = db.Column(db.Float, nullable=False)
    fecha_salida = db.Column(db.Date, nullable=True)
    estado_empleado = db.Column(db.Boolean, nullable=False)
    Puesto_id_puesto = db.Column(db.Integer, db.ForeignKey('puesto.id_puesto'), nullable=False)
    Usuario_id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'), unique=True, nullable=False)
    usuario = db.relationship('Usuario', back_populates='empleado')
    puesto = db.relationship('Puesto', back_populates='empleados')
    # ❗ Nueva relación: Un empleado puede tener muchas nóminas
    nominas = db.relationship('Nomina', back_populates='empleado')

    def __repr__(self):
        return f'<Empleado {self.nombre} {self.apellido_primero}>'

class Feriado(db.Model):
    __tablename__ = 'feriado'
    id_feriado = db.Column(db.Integer, primary_key=True)
    fecha_feriado = db.Column(db.Date, unique=True, nullable=False)
    descripcion_feriado = db.Column(db.String(255), nullable=True)
    registros_asistencia = db.relationship('RegistroAsistencia', back_populates='feriado_relacion')

    def __repr__(self):
        return f'<Feriado {self.fecha_feriado}>'


class TipoNomina(db.Model):
    """
    Modelo para la tabla que clasifica los tipos de nómina.
    """
    __tablename__ = 'tipo_nomina'
    id_tipo_nomina = db.Column(db.Integer, primary_key=True)
    nombre_tipo = db.Column(db.String(100), unique=True, nullable=False)
    
    # ❗ Corrección: Usamos back_populates y le decimos el nombre de la relación inversa
    nominas = db.relationship('Nomina', back_populates='tipo_nomina_relacion', lazy=True)

    def __repr__(self):
        return f'<TipoNomina {self.nombre_tipo}>'

# ❗ Nuevo modelo Nomina
class Nomina(db.Model):
    __tablename__ = 'nomina'
    id_nomina = db.Column(db.Integer, primary_key=True)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    salario_bruto = db.Column(db.Float, nullable=False)
    salario_neto = db.Column(db.Float, nullable=False)
    deducciones = db.Column(db.Float, nullable=False, default=0.0)
    estado_pago = db.Column(db.String(50), nullable=False, default='Pendiente')
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    
    # ❗ Aquí está tu clave foránea (asegúrate de que el nombre sea correcto)
    TipoNomina_id_tipo_nomina = db.Column(db.Integer, db.ForeignKey('tipo_nomina.id_tipo_nomina'), nullable=False)
    
    # Relaciones
    empleado = db.relationship('Empleado', back_populates='nominas')
    registros_asistencia = db.relationship('RegistroAsistencia', back_populates='nomina_relacion')
    
    # ❗ Corrección: Definimos la relación que se va a popular
    tipo_nomina_relacion = db.relationship('TipoNomina', back_populates='nominas', lazy=True)

    def __repr__(self):
        return f'<Nomina {self.id_nomina} del Empleado {self.Empleado_id_empleado}>'
    
class RegistroAsistencia(db.Model):
    __tablename__ = 'registro_asistencia'
    id_registro_asistencia = db.Column(db.Integer, primary_key=True)
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    fecha_registro = db.Column(db.Date, nullable=False)
    hora_entrada = db.Column(db.Time, nullable=False)
    hora_salida = db.Column(db.Time, nullable=True)
    hora_nominal = db.Column(db.Float, nullable=True)
    hora_extra = db.Column(db.Float, nullable=True)
    hora_feriado = db.Column(db.Float, nullable=True)
    estado_feriado = db.Column(db.Boolean, nullable=False, default=False)
    aprobacion_registro = db.Column(db.Boolean, nullable=False, default=False)
    
    # Claves foráneas
    Nomina_id_nomina = db.Column(db.Integer, db.ForeignKey('nomina.id_nomina'), nullable=True)
    Feriado_id_feriado = db.Column(db.Integer, db.ForeignKey('feriado.id_feriado'), nullable=True)

    # Relaciones
    feriado_relacion = db.relationship('Feriado', back_populates='registros_asistencia')
    # ❗ Nueva relación: Un registro de asistencia pertenece a una nómina
    nomina_relacion = db.relationship('Nomina', back_populates='registros_asistencia')

    def __repr__(self):
        return f'<RegistroAsistencia {self.id_registro_asistencia}>'
    
    # En payroll_app/models.py

class HistoricoNomina(db.Model):
    """
    Modelo para la tabla que almacena el historial de nóminas pagadas.
    """
    __tablename__ = 'historico_nomina'
    id_historico = db.Column(db.Integer, primary_key=True)
    fecha_historial = db.Column(db.Date, nullable=False)
    
    # Claves foráneas para relacionar con la nómina y el empleado
    Nomina_id_nomina = db.Column(db.Integer, db.ForeignKey('nomina.id_nomina'), nullable=False)
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    
    # Aquí puedes añadir campos para guardar una "fotografía" de los datos
    # al momento del pago, como el salario final, horas extra, etc.
    salario_bruto = db.Column(db.Float, nullable=False)
    salario_neto = db.Column(db.Float, nullable=False)
    deducciones = db.Column(db.Float, nullable=False)
    
    # Relaciones para acceder a los objetos Nomina y Empleado
    nomina_relacion = db.relationship('Nomina', backref='historicos', lazy=True)
    empleado_relacion = db.relationship('Empleado', backref='historico_nominas', lazy=True)

    def __repr__(self):
        return f'<HistoricoNomina {self.id_historico} para Nomina {self.Nomina_id_nomina}>'
    
class Aguinaldo(db.Model):
    """
    Modelo para la tabla que almacena el cálculo y el registro del aguinaldo.
    """
    __tablename__ = 'aguinaldo'
    id_aguinaldo = db.Column(db.Integer, primary_key=True)
    fecha_pago = db.Column(db.Date, nullable=False)
    monto = db.Column(db.Float, nullable=False)
    
    # Clave foránea que enlaza el aguinaldo con el empleado
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    
    # Relación para acceder al objeto Empleado
    empleado_relacion = db.relationship('Empleado', backref='aguinaldos', lazy=True)
    
    def __repr__(self):
        return f'<Aguinaldo {self.id_aguinaldo} para Empleado {self.Empleado_id_empleado}>'    

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
    
class Accion_Personal(db.Model):
    """
    Modelo para la tabla que registra las acciones de personal.
    """
    __tablename__ = 'accion_personal'
    id_accion = db.Column(db.Integer, primary_key=True)
    fecha_accion = db.Column(db.Date, nullable=False)
    detalles = db.Column(db.Text, nullable=True)

    # Claves foráneas para relacionar con el empleado y el tipo de acción
    Empleado_id_empleado = db.Column(db.Integer, db.ForeignKey('empleado.id_empleado'), nullable=False)
    Tipo_AP_id_tipo_ap = db.Column(db.Integer, db.ForeignKey('tipo_ap.id_tipo_ap'), nullable=False)

    # Relaciones para acceder a los objetos Empleado y Tipo_AP
    empleado = db.relationship('Empleado', backref='acciones_personales', lazy=True)
    tipo_ap = db.relationship('Tipo_AP', backref='acciones_personales', lazy=True)

    def __repr__(self):
        return f'<Accion_Personal {self.id_accion} para Empleado {self.Empleado_id_empleado}>'
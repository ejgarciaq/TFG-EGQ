from datetime import date, datetime, time
from werkzeug.security import generate_password_hash

from payroll_app import create_app, db
from payroll_app.models import (
    Accion_Personal,
    Aguinaldo,
    Configuracion,
    ConceptoNomina,
    Deduccion,
    Empleado,
    Feriado,
    Liquidacion,
    Nomina,
    Permiso,
    Puesto,
    RegistroAsistencia,
    Rol,
    TipoNomina,
    Usuario,
)


def get_or_create(model, defaults=None, **kwargs):
    instance = model.query.filter_by(**kwargs).first()
    if instance:
        return instance, False
    params = dict(kwargs)
    if defaults:
        params.update(defaults)
    instance = model(**params)
    db.session.add(instance)
    return instance, True


def seed():
    app = create_app()
    with app.app_context():
        print('Creando tablas si no existen...')
        db.create_all()

        # Roles y permisos
        admin_role, created = get_or_create(Rol, tipo_rol='admin', descripcion_rol='Administrador del sistema')
        employee_role, _ = get_or_create(Rol, tipo_rol='empleado', descripcion_rol='Empleado regular')

        permiso_nomina, _ = get_or_create(
            Permiso,
            nombre='ver_nomina',
            descripcion='Permite ver y generar nóminas'
        )
        permiso_empleado, _ = get_or_create(
            Permiso,
            nombre='gestion_empleado',
            descripcion='Permite crear y editar empleados'
        )

        if permiso_nomina not in admin_role.permisos:
            admin_role.permisos.append(permiso_nomina)
        if permiso_empleado not in admin_role.permisos:
            admin_role.permisos.append(permiso_empleado)

        # Puestos y tipos de nómina
        dev_puesto, _ = get_or_create(Puesto, tipo_puesto='Desarrollador')
        analista_puesto, _ = get_or_create(Puesto, tipo_puesto='Analista contable')
        mensual, _ = get_or_create(TipoNomina, nombre_tipo='Mensual')
        quincenal, _ = get_or_create(TipoNomina, nombre_tipo='Quincenal')

        # Configuración de ejemplo
        configs = [
            ('salario_minimo', '460000', 'float', 'Salario mínimo base para cálculos.'),
            ('porcentaje_isr', '15.00', 'float', 'Porcentaje de ISR aplicado por defecto.'),
            ('porcentaje_seguro_social', '9.34', 'float', 'Porcentaje de seguro social aplicado por defecto.'),
        ]
        for nombre, valor, tipo, descripcion in configs:
            _, _ = get_or_create(
                Configuracion,
                nombre_parametro=nombre,
                defaults={
                    'valor_parametro': valor,
                    'tipo_dato': tipo,
                    'descripcion': descripcion,
                }
            )

        db.session.commit()

        # Usuarios y empleados
        admin_user = Usuario.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = Usuario(
                username='admin',
                password=generate_password_hash('Admin123!'),
                estado_usuario=True,
                Rol_id_rol=admin_role.id_rol,
                intentos_fallidos=0,
                cambio_password_requerido=False,
            )
            db.session.add(admin_user)
            db.session.flush()
            admin_employee = Empleado(
                nombre='Admin',
                apellido_primero='Sistema',
                apellido_segundo='Demo',
                cedula='000000000',
                correo='admin@demo.local',
                telefono='88880000',
                fecha_ingreso=date(2020, 1, 1),
                salario_base=800000.0,
                estado_empleado=True,
                Puesto_id_puesto=dev_puesto.id_puesto,
                TipoNomina_id_tipo_nomina=mensual.id_tipo_nomina,
                Usuario_id_usuario=admin_user.id_usuario,
                vacaciones_disponibles=15,
            )
            db.session.add(admin_employee)
        else:
            admin_employee = Empleado.query.filter_by(Usuario_id_usuario=admin_user.id_usuario).first()

        user_jane = Usuario.query.filter_by(username='jane.doe').first()
        if not user_jane:
            user_jane = Usuario(
                username='jane.doe',
                password=generate_password_hash('Empleado123!'),
                estado_usuario=True,
                Rol_id_rol=employee_role.id_rol,
                intentos_fallidos=0,
                cambio_password_requerido=False,
            )
            db.session.add(user_jane)
            db.session.flush()
            empleado_jane = Empleado(
                nombre='Jane',
                apellido_primero='Doe',
                apellido_segundo='Demo',
                cedula='123456789',
                correo='jane.doe@demo.local',
                telefono='88776655',
                fecha_ingreso=date(2023, 3, 1),
                salario_base=520000.0,
                estado_empleado=True,
                Puesto_id_puesto=analista_puesto.id_puesto,
                TipoNomina_id_tipo_nomina=mensual.id_tipo_nomina,
                Usuario_id_usuario=user_jane.id_usuario,
                vacaciones_disponibles=10,
            )
            db.session.add(empleado_jane)
        else:
            empleado_jane = Empleado.query.filter_by(Usuario_id_usuario=user_jane.id_usuario).first()

        db.session.commit()

        # Feriados de ejemplo
        feriado_navidad, _ = get_or_create(
            Feriado,
            fecha_feriado=date(2025, 12, 25),
            defaults={'descripcion_feriado': 'Navidad', 'pago_obligatorio': True}
        )
        feriado_independencia, _ = get_or_create(
            Feriado,
            fecha_feriado=date(2025, 9, 15),
            defaults={'descripcion_feriado': 'Día de la Independencia', 'pago_obligatorio': True}
        )

        db.session.commit()

        # Nómina de ejemplo para Jane
        if empleado_jane:
            nomina_jane = Nomina.query.filter_by(Empleado_id_empleado=empleado_jane.id_empleado).first()
            if not nomina_jane:
                nomina_jane = Nomina(
                    fecha_inicio=date(2025, 4, 1),
                    fecha_fin=date(2025, 4, 30),
                    salario_bruto=empleado_jane.salario_base,
                    salario_neto=empleado_jane.salario_base * 0.82,
                    deducciones=empleado_jane.salario_base * 0.18,
                    pago_obligatorio=False,
                    fecha_creacion=datetime.now(),
                    Empleado_id_empleado=empleado_jane.id_empleado,
                    TipoNomina_id_tipo_nomina=mensual.id_tipo_nomina,
                )
                db.session.add(nomina_jane)
                db.session.flush()
                db.session.add(Deduccion(
                    Nomina_id_nomina=nomina_jane.id_nomina,
                    tipo_deduccion='ISR',
                    monto=empleado_jane.salario_base * 0.10,
                    porcentaje=10.0,
                ))
                db.session.add(Deduccion(
                    Nomina_id_nomina=nomina_jane.id_nomina,
                    tipo_deduccion='CCSS',
                    monto=empleado_jane.salario_base * 0.08,
                    porcentaje=8.0,
                ))
                db.session.add(ConceptoNomina(
                    Nomina_id_nomina=nomina_jane.id_nomina,
                    tipo_concepto='Bono',
                    dias=0,
                    monto=20000.0,
                    descripcion='Bono por cumplimiento de metas',
                ))

        db.session.commit()

        # Registros de asistencia de ejemplo
        if empleado_jane:
            registro = RegistroAsistencia.query.filter_by(Empleado_id_empleado=empleado_jane.id_empleado, fecha_registro=date(2025, 4, 3)).first()
            if not registro:
                db.session.add(RegistroAsistencia(
                    fecha_registro=date(2025, 4, 3),
                    hora_entrada=time(8, 0),
                    hora_salida=time(17, 0),
                    hora_entrada_almuerzo=time(12, 0),
                    hora_salida_almuerzo=time(13, 0),
                    total_horas=8.0,
                    hora_nominal=8.0,
                    hora_extra=0.0,
                    hora_feriado=0.0,
                    monto_pago=empleado_jane.salario_base / 22,
                    aprobacion_registro=True,
                    Empleado_id_empleado=empleado_jane.id_empleado,
                    Nomina_id_nomina=nomina_jane.id_nomina,
                ))

        db.session.commit()

        # Liquidación demo
        if empleado_jane:
            if not Liquidacion.query.filter_by(Empleado_id_empleado=empleado_jane.id_empleado).first():
                db.session.add(Liquidacion(
                    fecha_pago=date(2025, 5, 15),
                    fecha_fin_contrato=date(2025, 5, 15),
                    total_monto=empleado_jane.salario_base * 1.2,
                    monto_preaviso=empleado_jane.salario_base * 0.25,
                    monto_cesantia=empleado_jane.salario_base * 0.25,
                    monto_vacaciones=empleado_jane.salario_base * 0.10,
                    monto_aguinaldo=empleado_jane.salario_base * 0.20,
                    monto_salario_pendiente=0.0,
                    Empleado_id_empleado=empleado_jane.id_empleado,
                ))

        db.session.commit()

        print('Demo inicializado con éxito.')
        print('Credenciales de demo:')
        print(' - admin / Admin123!')
        print(' - jane.doe / Empleado123!')


if __name__ == '__main__':
    seed()

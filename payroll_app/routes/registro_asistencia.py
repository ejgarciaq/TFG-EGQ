from flask import Blueprint, logging, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from payroll_app.routes.decorators import permiso_requerido
from sqlalchemy import func
from payroll_app.models import db, RegistroAsistencia, Feriado, Empleado, Nomina, TipoNomina, Tipo_AP, Accion_Personal
from datetime import datetime, date, time, timedelta
import os
from werkzeug.utils import secure_filename # Importar para nombres de archivo seguros


# El nombre del blueprint es 'registro_asistencia'
registro_asistencia_bp = Blueprint('registro_asistencia', __name__)

# Configuración de la carpeta de subida de documentos
UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads'))
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Extensiones de archivo permitidas
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    """Función para validar la extensión del archivo."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ------------------------- Lógica de Aprobación ------------------------------

@registro_asistencia_bp.route('/procesar_aprobacion', methods=['POST'])
#@permiso_requerido('aprobar_horas_extras')
@login_required
def procesar_aprobacion():
    """Procesa la aprobación masiva o individual de registros de horas extras."""
    try:
        registros_seleccionados_ids = request.form.getlist('registros_seleccionados')
        accion = request.form.get('accion_masiva')

        if not registros_seleccionados_ids:
            flash('No ha seleccionado ningún registro.', 'warning')
            return redirect(url_for('registro_asistencia.listar_asistencia'))

        for registro_id in registros_seleccionados_ids:
            registro = RegistroAsistencia.query.get(registro_id)
            if registro:
                if accion == 'aprobar_masiva':
                    registro.aprobacion_registro = True
                elif accion == 'rechazar_masiva':
                    registro.aprobacion_registro = False
        
        db.session.commit()
        flash('Registros de horas extras actualizados exitosamente.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al procesar la aprobación: {str(e)}', 'danger')
    
    return redirect(url_for('registro_asistencia.listar_asistencia'))


# ------------------------- Aprobar Horas Extras ------------------------------

@registro_asistencia_bp.route('/aprobar_horas_extras')
#@permiso_requerido('aprobar_horas_extras')
@login_required
def aprobar_horas_extras():
    """
    Muestra los registros de asistencia con horas extras pendientes de aprobación.
    """
    try:
        page = request.args.get('page', 1, type=int)
        registros_pendientes = RegistroAsistencia.query.filter(
            RegistroAsistencia.hora_extra > 0,
            RegistroAsistencia.aprobacion_registro == False
        ).order_by(RegistroAsistencia.fecha_registro.desc()).paginate(
            page=page, per_page=15, error_out=False
        )
        
        # Se usa la plantilla de listado general
        return render_template('listar_asistencia.html', registros=registros_pendientes)
        
    except Exception as e:
        flash(f'Ocurrió un error al cargar los registros de horas extras: {str(e)}', 'danger')
        return redirect(url_for('registro_asistencia.listar_asistencia'))


# Ver asistencia pantalla control de marcas ----------------------------------------------------
@registro_asistencia_bp.route('/asistencia', methods=['GET'])
@login_required
def ver_asistencia():
    return render_template('registro_asistencia.html')


# registrar asistencia -------------------------------
@registro_asistencia_bp.route('/asistencia/registrar', methods=['POST'])
@login_required 
def registrar_asistencia():
    empleado = Empleado.query.filter_by(Usuario_id_usuario=current_user.id_usuario).first()

    if not empleado:
        flash('Error de autenticación: No se encontró el empleado asociado a tu cuenta. Contacta al administrador.', 'danger')
        return redirect(url_for('registro_asistencia.ver_asistencia'))
    
    ahora = datetime.now()
    fecha_registro = ahora.date()
    hora_registro = ahora.time()
    
    # Lógica para MARCAR SALIDA
    # Se busca un registro del día de hoy o, en caso de turno nocturno, del día anterior
    ayer = fecha_registro - timedelta(days=1)
    
    registro_activo = RegistroAsistencia.query.filter(
        RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
        RegistroAsistencia.hora_salida.is_(None),
        RegistroAsistencia.fecha_registro.in_([fecha_registro, ayer])
    ).first()

    try:
        if registro_activo:
            # Validación: No permitir registro de salida en menos de 30 minutos
            ultimo_momento = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada)
            tiempo_transcurrido = ahora - ultimo_momento
            
            if tiempo_transcurrido < timedelta(minutes=30):
                flash('No puedes registrar una salida en menos de 30 minutos desde tu entrada.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))
            
            registro_activo.hora_salida = hora_registro

            # --- CÁLCULO DE HORAS Y MONTO (UNIFICADO) ---
            HORA_NOMINAL_ESTANDAR = 8.0
            PAUSA_ALMUERZO = timedelta(minutes=60)
            JORNADA_MINIMA_PAUSA = timedelta(hours=6)

            dt_entrada = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada)
            dt_salida = datetime.combine(fecha_registro, hora_registro)
            
            # Manejar turnos nocturnos
            if dt_salida < dt_entrada:
                dt_salida += timedelta(days=1)
            
            # Calcular total de horas trabajadas y aplicar pausa
            total_time_delta = dt_salida - dt_entrada
            if total_time_delta > JORNADA_MINIMA_PAUSA:
                total_time_delta -= PAUSA_ALMUERZO
            registro_activo.total_horas = round(total_time_delta.total_seconds() / 3600, 2)
            
            # Obtener información del empleado y feriado
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=fecha_registro).first()
            registro_activo.Feriado_id_feriado = es_feriado_hoy.id_feriado if es_feriado_hoy else None
            
            # Calcular costo por hora (normal, extra, feriado)
            horas_mensuales = 30 * HORA_NOMINAL_ESTANDAR
            costo_por_hora_normal = empleado.salario_base / horas_mensuales if horas_mensuales else 0
            costo_por_hora_extra = costo_por_hora_normal * 1.5
            costo_por_hora_feriado = costo_por_hora_normal * 2

            # Calcular horas extra y horas feriado
            horas_nominales_trabajadas = min(registro_activo.total_horas, HORA_NOMINAL_ESTANDAR)
            registro_activo.hora_extra = max(0, registro_activo.total_horas - HORA_NOMINAL_ESTANDAR)
            registro_activo.hora_feriado = 0

            # Lógica de pago: feriado vs. día normal
            if es_feriado_hoy and es_feriado_hoy.pago_obligatorio:
                pago_base_feriado = HORA_NOMINAL_ESTANDAR * costo_por_hora_normal
                pago_adicional_feriado = registro_activo.total_horas * costo_por_hora_feriado
                registro_activo.monto_pago = round(pago_base_feriado + pago_adicional_feriado, 2)
                registro_activo.hora_feriado = registro_activo.total_horas
                registro_activo.hora_extra = 0
            else:
                monto_pago = (horas_nominales_trabajadas * costo_por_hora_normal) + \
                             (registro_activo.hora_extra * costo_por_hora_extra)
                registro_activo.monto_pago = round(monto_pago, 2)

            # Marcar el registro para aprobación si hay horas extra o feriado
            if registro_activo.hora_extra > 0 or registro_activo.hora_feriado > 0:
                registro_activo.aprobacion_registro = False
            else:
                registro_activo.aprobacion_registro = True
            
            # --- FIN DEL CÁLCULO ---
            
            db.session.commit()
            flash('¡Salida registrada exitosamente! Tu jornada ha finalizado.', 'success')
            return redirect(url_for('registro_asistencia.ver_asistencia'))

        # Lógica para MARCAR ENTRADA (VALIDACIÓN CORREGIDA)
        else:
            # Validar si ya existe CUALQUIER registro de asistencia para el día de hoy
            registro_de_hoy = RegistroAsistencia.query.filter_by(
                Empleado_id_empleado=empleado.id_empleado,
                fecha_registro=fecha_registro
            ).first()

            if registro_de_hoy:
                flash('Ya has registrado tu jornada de hoy. No se permite más de una entrada por día.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))
            
            # Si no hay registro activo y no hay entrada hoy, crear una nueva
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=fecha_registro).first()
            feriado_id = es_feriado_hoy.id_feriado if es_feriado_hoy else None
            
            nuevo_registro = RegistroAsistencia(
                Empleado_id_empleado=empleado.id_empleado,
                fecha_registro=fecha_registro,
                hora_entrada=hora_registro,
                Feriado_id_feriado=feriado_id,
                aprobacion_registro=False,
            )
            db.session.add(nuevo_registro)
            db.session.commit()
            flash('¡Entrada registrada exitosamente! Tu jornada ha comenzado.', 'success')
            return redirect(url_for('registro_asistencia.ver_asistencia'))

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error al registrar la asistencia: {str(e)}")
        flash('Ocurrió un error al registrar la asistencia. Por favor, inténtelo de nuevo.', 'danger')

    return redirect(url_for('registro_asistencia.ver_asistencia'))

#----------- Mantenimiento ------------------------------

# listar registros
@registro_asistencia_bp.route('/listar_asistencia')
@permiso_requerido('listar_asistencia')
@login_required
def listar_asistencia():
    # Obtener todos los registros de asistencia ordenados por fecha con paginación
    page = request.args.get('page', 1, type=int)
    registros = RegistroAsistencia.query.order_by(RegistroAsistencia.fecha_registro.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    return render_template('listar_asistencia.html', registros=registros)

# Editar registro de asistencia
@registro_asistencia_bp.route('/editar/<int:registro_id>', methods=['GET', 'POST'])
@permiso_requerido('editar_asistencia')
@login_required
def editar_asistencia(registro_id):
    registro = RegistroAsistencia.query.get_or_404(registro_id)

    if request.method == 'POST':
        try:
            # 1. Asignar los valores de fecha y hora de entrada (siempre son requeridos)
            nueva_fecha = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
            nueva_hora_entrada = datetime.strptime(request.form['hora_entrada'], '%H:%M:%S').time()
            
            # 2. VALIDACIÓN CLAVE: Verificar si la hora de salida está vacía
            if not request.form.get('hora_salida'):
                # Caso A: El registro se deja abierto (sin hora de salida)
                
                # Asignar los nuevos valores al objeto
                registro.fecha_registro = nueva_fecha
                registro.hora_entrada = nueva_hora_entrada
                registro.hora_salida = None  # Importante: Establecer la hora de salida a None
                registro.aprobacion_registro = False # Un registro abierto no puede estar aprobado
                
                # Campos de cálculo a None o 0
                registro.total_horas = None
                registro.hora_extra = 0.0
                registro.hora_feriado = 0.0
                registro.monto_pago = 0.0
                
                flash('Registro de entrada actualizado. La jornada queda abierta, sin hora de salida.', 'info')
                
            else:
                # Caso B: El registro se completa (con hora de salida)
                nueva_hora_salida = datetime.strptime(request.form['hora_salida'], '%H:%M:%S').time()

                # Validar que la hora de salida no sea anterior a la de entrada
                dt_entrada_base = datetime.combine(nueva_fecha, nueva_hora_entrada)
                dt_salida_base = datetime.combine(nueva_fecha, nueva_hora_salida)

                if dt_salida_base < dt_entrada_base:
                    flash('Error: La hora de salida no puede ser anterior a la hora de entrada. Esto no es válido para turnos que no sean nocturnos.', 'danger')
                    return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro.id_registro_asistencia))

                # Asignar los valores al objeto del registro
                registro.fecha_registro = nueva_fecha
                registro.hora_entrada = nueva_hora_entrada
                registro.hora_salida = nueva_hora_salida
                registro.aprobacion_registro = 'aprobado' in request.form
                
                # Recalcular todos los valores (total_horas, hora_extra, monto_pago)
                HORA_NOMINAL_ESTANDAR = 8.0
                PAUSA_ALMUERZO = timedelta(minutes=60)
                JORNADA_MINIMA_PAUSA = timedelta(hours=6)
                
                dt_entrada = datetime.combine(registro.fecha_registro, registro.hora_entrada)
                dt_salida = datetime.combine(registro.fecha_registro, registro.hora_salida)

                if dt_salida < dt_entrada:
                    dt_salida += timedelta(days=1)
                
                total_time_delta = dt_salida - dt_entrada
                if total_time_delta > JORNADA_MINIMA_PAUSA:
                    total_time_delta -= PAUSA_ALMUERZO
                registro.total_horas = round(total_time_delta.total_seconds() / 3600, 2)
                
                empleado = Empleado.query.get(registro.Empleado_id_empleado)
                es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=registro.fecha_registro).first()
                registro.Feriado_id_feriado = es_feriado_hoy.id_feriado if es_feriado_hoy else None
                
                horas_nominales_trabajadas = min(registro.total_horas, HORA_NOMINAL_ESTANDAR)
                registro.hora_extra = max(0, registro.total_horas - HORA_NOMINAL_ESTANDAR)
                registro.hora_feriado = 0

                horas_mensuales = 30 * HORA_NOMINAL_ESTANDAR
                costo_por_hora_normal = empleado.salario_base / horas_mensuales if horas_mensuales else 0
                costo_por_hora_extra = costo_por_hora_normal * 1.5
                costo_por_hora_feriado = costo_por_hora_normal * 2

                if es_feriado_hoy and es_feriado_hoy.pago_obligatorio:
                    pago_base_feriado = HORA_NOMINAL_ESTANDAR * costo_por_hora_normal
                    pago_por_trabajar_feriado = registro.total_horas * costo_por_hora_feriado
                    registro.monto_pago = round(pago_base_feriado + pago_por_trabajar_feriado, 2)
                    registro.hora_feriado = registro.total_horas
                    registro.hora_extra = 0
                else:
                    monto_pago = (horas_nominales_trabajadas * costo_por_hora_normal) + \
                                 (registro.hora_extra * costo_por_hora_extra) + \
                                 (registro.hora_feriado * costo_por_hora_feriado)
                    registro.monto_pago = round(monto_pago, 2)
                
                flash('Registro de asistencia actualizado y recalculado exitosamente.', 'success')

            db.session.commit()
            return redirect(url_for('registro_asistencia.listar_asistencia'))
        
        except ValueError:
            db.session.rollback()
            flash('Formato de fecha u hora incorrecto. Use el formato YYYY-MM-DD y HH:MM:SS.', 'danger')
            return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro.id_registro_asistencia))
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al actualizar el registro: {str(e)}', 'danger')
            return redirect(url_for('registro_asistencia.listar_asistencia'))

    return render_template('editar_asistencia.html', registro=registro)

#Eliminar registro
@registro_asistencia_bp.route('/eliminar/<int:registro_id>', methods=['POST'])
@permiso_requerido('eliminar_asistencia')
@login_required
def eliminar_asistencia(registro_id):
    registro = RegistroAsistencia.query.get_or_404(registro_id)

    try:
        db.session.delete(registro)
        db.session.commit()
        flash('Registro de asistencia eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al eliminar el registro: {str(e)}', 'danger')

    return redirect(url_for('registro_asistencia.listar_asistencia'))


# -------------------------   Generar Planilla Planilla 

@registro_asistencia_bp.route('/generar_nomina', methods=['GET', 'POST'])
@permiso_requerido('generar_nomina')
@login_required
def generar_nomina():
    """Muestra el formulario, la lista de nóminas, y procesa la generación."""
    tipos_nomina = TipoNomina.query.all()
    
    if request.method == 'POST':
        try:
            fecha_inicio_str = request.form.get('fecha_inicio')
            fecha_fin_str = request.form.get('fecha_fin')
            id_tipo_nomina = request.form.get('tipo_nomina_id')

            if not id_tipo_nomina:
                flash('Debe seleccionar un tipo de nómina.', 'danger')
            else:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
                
                empleados = Empleado.query.filter_by(TipoNomina_id_tipo_nomina=id_tipo_nomina).all()
                
                if not empleados:
                    flash('No se encontraron empleados para el tipo de nómina seleccionado.', 'warning')
                else:
                    for empleado in empleados:
                        total_monto_bruto = db.session.query(func.sum(RegistroAsistencia.monto_pago)).filter(
                            RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                            RegistroAsistencia.fecha_registro.between(fecha_inicio, fecha_fin)
                        ).scalar() or 0
                        
                        deducciones = total_monto_bruto * 0.105
                        monto_neto = total_monto_bruto - deducciones
                        
                        nueva_nomina = Nomina(
                            Empleado_id_empleado=empleado.id_empleado,
                            fecha_inicio=fecha_inicio,
                            fecha_fin=fecha_fin,
                            salario_bruto=round(total_monto_bruto, 2),
                            salario_neto=round(monto_neto, 2),
                            deducciones=round(deducciones, 2),
                            TipoNomina_id_tipo_nomina=id_tipo_nomina,
                            fecha_creacion=datetime.now()
                        )
                        db.session.add(nueva_nomina)
                    
                    db.session.commit()
                    flash('Nómina generada y guardada exitosamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al generar la nómina: {str(e)}', 'danger')

    # Al final de la función, recupera todas las nóminas para mostrarlas.
    # Esto se ejecuta tanto en el GET inicial como después de un POST exitoso.
    nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
    return render_template('generar_nomina.html', nominas=nominas, tipos_nomina=tipos_nomina)
        
@registro_asistencia_bp.route('/listar_nominas')
@permiso_requerido('listar_nominas')
@login_required
def listar_nominas():
    """Muestra una lista de todas las nóminas generadas."""
    try:
        nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
        tipos_nomina = TipoNomina.query.all()
        return render_template('generar_nomina.html', nominas=nominas, tipos_nomina=tipos_nomina)
    except Exception as e:
        flash(f'Ocurrió un error al cargar las nóminas: {str(e)}', 'danger')
        tipos_nomina = TipoNomina.query.all()
        return render_template('generar_nomina.html', nominas=[], tipos_nomina=tipos_nomina)
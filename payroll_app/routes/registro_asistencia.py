from flask import Blueprint, logging, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from payroll_app.routes.decorators import permiso_requerido
from sqlalchemy import func
from payroll_app.models import db, RegistroAsistencia, Feriado, Empleado, Nomina, TipoNomina, Tipo_AP, Accion_Personal
from datetime import datetime, date, time, timedelta
import os, logging
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
    empleado = Empleado.query.filter_by(Usuario_id_usuario=current_user.id_usuario).first()
    if not empleado:
        flash('Error de autenticación: No se encontró el empleado asociado a tu cuenta. Contacta al administrador.', 'danger')
        return redirect(url_for('main.index')) 

    ahora = datetime.now()
    fecha_hoy = ahora.date()

    # --- Lógica para determinar el estado del botón (Responsabilidad 1) ---
    estado_actual = 'entrada' # Valor por defecto inicial, si no se encuentra ningún registro activo o finalizado de hoy

    # 1. Buscar el registro activo (sin hora_salida) para el empleado HOY.
    #    Este es el que determina en qué "paso" de la jornada está el empleado.
    registro_activo = RegistroAsistencia.query.filter(
        RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
        RegistroAsistencia.fecha_registro == fecha_hoy,
        RegistroAsistencia.hora_salida.is_(None) 
    ).order_by(RegistroAsistencia.fecha_registro.desc(), RegistroAsistencia.hora_entrada.desc()).first()

    if registro_activo:

        # Determinar el estado basándose en los campos del registro activo
        if not registro_activo.hora_entrada_almuerzo:
            estado_actual = 'salida_almuerzo' 
            print(f"DEBUG (ver_asistencia): Estado determinado: '{estado_actual}' (No ha marcado salida a almuerzo).")
        elif registro_activo.hora_entrada_almuerzo and not registro_activo.hora_salida_almuerzo:
            estado_actual = 'regreso_almuerzo' 
            print(f"DEBUG (ver_asistencia): Estado determinado: '{estado_actual}' (Salió a almorzar, aún no regresó).")
        elif registro_activo.hora_entrada_almuerzo and registro_activo.hora_salida_almuerzo and not registro_activo.hora_salida:
            estado_actual = 'salida_final' 
            print(f"DEBUG (ver_asistencia): Estado determinado: '{estado_actual}' (Regresó del almuerzo, aún no finalizó).")
        else:
            # Esto NO debería pasar si 'hora_salida.is_(None)' es correcto
            # Si un registro está aquí, significa que tiene hora_entrada, ambas de almuerzo, y NO hora_salida.
            # Esta rama ya es una especie de 'salida_final', pero la anterior la cubriría.
            # Es un fallback para casos inesperados.
            estado_actual = 'salida_final' # Podría ser un error lógico si llega aquí
    else:
        # Si no hay un registro ACTIVO HOY, verificamos si ya FINALIZÓ su jornada HOY
        registro_finalizado_hoy = RegistroAsistencia.query.filter(
            RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
            RegistroAsistencia.fecha_registro == fecha_hoy,
            RegistroAsistencia.hora_salida.isnot(None) # Busca un registro de hoy que ya finalizó
        ).first()
        
        if registro_finalizado_hoy:
            print(f"DEBUG (ver_asistencia): Se encontró un registro FINALIZADO para HOY. Estado: 'jornada_completa_hoy'.")
            estado_actual = 'jornada_completa_hoy' 
            flash('Ya has completado tu jornada de hoy. No se permite más de una entrada por día.', 'info')
        else:
            print(f"DEBUG (ver_asistencia): No se encontró ningún registro finalizado para HOY. Se asume estado: 'entrada'.")
            # Si no hay registro activo Y no hay registro finalizado, significa que el empleado puede marcar 'entrada'.
            estado_actual = 'entrada' 
    
    # Validación final para asegurar que el estado determinado sea uno de los conocidos por el JS
    estados_validos = ['entrada', 'salida_almuerzo', 'regreso_almuerzo', 'salida_final', 'jornada_completa_hoy']
    if estado_actual not in estados_validos:
        estado_actual = 'entrada' 

    print(f"DEBUG (ver_asistencia): Estado actual FINAL que se envía al template: '{estado_actual}'") 

    # --- Lógica para listar la asistencia en una tabla (Responsabilidad 2) ---
    # Recuperar registros de asistencia para el empleado (ej. los últimos 30 días)
    # Puedes ajustar el rango de fechas según lo necesites (ej. solo el mes actual, o los últimos 7 días)
    fecha_inicio_rango = fecha_hoy - timedelta(days=30) # Ej: los últimos 30 días
    
    registros_asistencia_display = RegistroAsistencia.query.filter(
        RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
        RegistroAsistencia.fecha_registro >= fecha_inicio_rango
    ).order_by(RegistroAsistencia.fecha_registro.desc(), RegistroAsistencia.hora_entrada.desc()).all()

    return render_template('registro_asistencia.html', 
                           estado_actual=estado_actual,
                           registros=registros_asistencia_display)


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

    # Obtener la acción del formulario
    accion = request.form.get('accion')

    try:
        if accion == 'entrada':
            registro_incompleto_existente = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.hora_salida.is_(None)
            ).first()

            if registro_incompleto_existente:
                if registro_incompleto_existente.fecha_registro == fecha_registro:
                    flash('Ya tienes una jornada activa para hoy. Si necesitas marcar una pausa o finalizar, usa el botón correspondiente.', 'warning')
                    return redirect(url_for('registro_asistencia.ver_asistencia'))
                else:
                    flash(f'Advertencia: Tienes una jornada sin finalizar del día {registro_incompleto_existente.fecha_registro.strftime("%d/%m/%Y")}. Por favor, contacta al administrador para resolverlo. Registrando tu entrada de hoy.', 'warning')
            
            registro_finalizado_hoy = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.fecha_registro == fecha_registro,
                RegistroAsistencia.hora_salida.isnot(None)
            ).first()

            if registro_finalizado_hoy:
                flash('Ya has completado tu jornada de hoy. No se permite más de una entrada por día.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))
            
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=fecha_registro).first()
            feriado_id = es_feriado_hoy.id_feriado if es_feriado_hoy else None

            nuevo_registro = RegistroAsistencia(
                Empleado_id_empleado=empleado.id_empleado,
                fecha_registro=fecha_registro,
                hora_entrada=hora_registro,
                Feriado_id_feriado=feriado_id,
                aprobacion_registro=False,
                hora_entrada_almuerzo=None,
                hora_salida_almuerzo=None
            )
            db.session.add(nuevo_registro)
            db.session.commit()
            flash('¡Entrada registrada exitosamente! Tu jornada ha comenzado.', 'success')

        elif accion == 'salida_almuerzo':
            registro_activo = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.fecha_registro == fecha_registro,
                RegistroAsistencia.hora_entrada.isnot(None),
                RegistroAsistencia.hora_salida.is_(None),
                RegistroAsistencia.hora_entrada_almuerzo.is_(None)
            ).first()

            if registro_activo:
                dt_entrada = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada)
                if ahora - dt_entrada < timedelta(minutes=30):
                    flash('No puedes marcar la salida al almuerzo tan pronto después de la entrada (mínimo 30 minutos).', 'warning')
                    return redirect(url_for('registro_asistencia.ver_asistencia'))

                registro_activo.hora_entrada_almuerzo = hora_registro
                db.session.commit()
                flash('¡Salida para el almuerzo registrada!', 'info')
            else:
                flash('No puedes marcar la salida al almuerzo. Asegúrate de haber iniciado tu jornada y no haber marcado ya el almuerzo.', 'warning')

        elif accion == 'regreso_almuerzo':
            registro_activo = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.fecha_registro == fecha_registro,
                RegistroAsistencia.hora_entrada.isnot(None),
                RegistroAsistencia.hora_salida.is_(None),
                RegistroAsistencia.hora_entrada_almuerzo.isnot(None),
                RegistroAsistencia.hora_salida_almuerzo.is_(None)
            ).first()

            if registro_activo:
                dt_entrada_almuerzo = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada_almuerzo)
                if ahora < dt_entrada_almuerzo + timedelta(minutes=1):
                    flash('La hora de regreso del almuerzo no puede ser anterior o demasiado cercana a la hora de salida.', 'warning')
                    return redirect(url_for('registro_asistencia.ver_asistencia'))

                registro_activo.hora_salida_almuerzo = hora_registro
                db.session.commit()
                flash('¡Regreso del almuerzo registrado!', 'info')
            else:
                flash('No puedes marcar el regreso del almuerzo. Asegúrate de haber marcado la salida al almuerzo y de tener una jornada activa.', 'warning')

        elif accion == 'salida_final':
            ayer = fecha_registro - timedelta(days=1)
            registro_activo = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.hora_salida.is_(None),
                RegistroAsistencia.fecha_registro.in_([fecha_registro, ayer])
            ).first()

            if not registro_activo:
                flash('No hay una entrada de jornada activa para registrar la salida. Por favor, asegúrate de haber marcado tu entrada.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))

            dt_entrada = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada)
            
            dt_salida_actual_temp = datetime.combine(fecha_registro, hora_registro)
            if dt_salida_actual_temp < dt_entrada:
                dt_salida_actual_temp += timedelta(days=1)
            
            tiempo_transcurrido_desde_entrada = dt_salida_actual_temp - dt_entrada

            if tiempo_transcurrido_desde_entrada < timedelta(minutes=30):
                flash('No puedes registrar una salida final en menos de 30 minutos desde tu entrada.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))

            if registro_activo.hora_entrada_almuerzo and not registro_activo.hora_salida_almuerzo:
                flash('Debes registrar el regreso del almuerzo antes de finalizar la jornada.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))

            registro_activo.hora_salida = hora_registro

            HORA_NOMINAL_ESTANDAR = 8.0
            JORNADA_MINIMA_PAUSA_OBLIGATORIA = timedelta(hours=6)

            dt_entrada = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada)
            dt_salida = datetime.combine(fecha_registro, hora_registro)

            if dt_salida < dt_entrada:
                dt_salida += timedelta(days=1)

            total_time_bruto = dt_salida - dt_entrada

            pausa_real_almuerzo = timedelta(minutes=0)
            if registro_activo.hora_entrada_almuerzo and registro_activo.hora_salida_almuerzo:
                dt_entrada_almuerzo = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada_almuerzo)
                dt_salida_almuerzo = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_salida_almuerzo)
                
                if dt_salida_almuerzo < dt_entrada_almuerzo:
                    dt_salida_almuerzo += timedelta(days=1)
                
                pausa_real_almuerzo = dt_salida_almuerzo - dt_entrada_almuerzo
            
            total_time_neto = total_time_bruto
            if pausa_real_almuerzo > timedelta(minutes=0):
                 total_time_neto -= pausa_real_almuerzo
            elif total_time_bruto > JORNADA_MINIMA_PAUSA_OBLIGATORIA:
                 total_time_neto -= timedelta(minutes=60)
            
            registro_activo.total_horas = round(total_time_neto.total_seconds() / 3600, 2)

            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=registro_activo.fecha_registro).first()
            registro_activo.Feriado_id_feriado = es_feriado_hoy.id_feriado if es_feriado_hoy else None

            horas_mensuales = 30 * HORA_NOMINAL_ESTANDAR
            costo_por_hora_normal = empleado.salario_base / horas_mensuales if horas_mensuales else 0
            costo_por_hora_extra = costo_por_hora_normal * 1.5
            costo_por_hora_feriado = costo_por_hora_normal * 2

            horas_nominales_trabajadas = min(registro_activo.total_horas, HORA_NOMINAL_ESTANDAR)
            registro_activo.hora_extra = max(0, registro_activo.total_horas - HORA_NOMINAL_ESTANDAR)
            registro_activo.hora_feriado = 0

            if es_feriado_hoy and es_feriado_hoy.pago_obligatorio:
                registro_activo.monto_pago = round(registro_activo.total_horas * costo_por_hora_feriado, 2)
                registro_activo.hora_feriado = registro_activo.total_horas
                registro_activo.hora_extra = 0
            else:
                monto_pago = (horas_nominales_trabajadas * costo_por_hora_normal) + \
                             (registro_activo.hora_extra * costo_por_hora_extra)
                registro_activo.monto_pago = round(monto_pago, 2)

            if registro_activo.hora_extra > 0 or registro_activo.hora_feriado > 0:
                registro_activo.aprobacion_registro = False
            else:
                registro_activo.aprobacion_registro = True

            db.session.commit()
            flash('¡Salida registrada exitosamente! Tu jornada ha finalizado.', 'success')

        else:
            flash('Acción no reconocida o no válida.', 'danger')

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error al registrar la asistencia para empleado {empleado.id_empleado}: {str(e)}")
        flash(f'Ocurrió un error al registrar la asistencia. Por favor, inténtelo de nuevo. Detalle: {str(e)}', 'danger')
    
    return redirect(url_for('registro_asistencia.ver_asistencia'))

#----------- Mantenimiento ------------------------------

# listar registros-----------------------------------------

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

# Editar registro de asistencia ---------------------------------------------------------------------------

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

#Eliminar registro --------------------------------------------------------------

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


# -------------------------   Generar Planilla Planilla ------------------------------

@registro_asistencia_bp.route('/generar_nomina', methods=['GET', 'POST'])
@permiso_requerido('listar_nominas')
@login_required
def generar_nomina():
    """
    Procesa la generación de nóminas calculando el salario bruto y las deducciones
    (SEM, IVM, LPT, Renta), ajustando por la frecuencia de nómina.
    """
    tipos_nomina = TipoNomina.query.all()
    
    fecha_inicio_seleccionada = None
    fecha_fin_seleccionada = None
    id_tipo_nomina_seleccionado = None

    if request.method == 'POST':
        try:
            fecha_inicio_str = request.form.get('fecha_inicio')
            fecha_fin_str = request.form.get('fecha_fin')
            id_tipo_nomina_str = request.form.get('tipo_nomina_id')

            fecha_inicio_seleccionada = fecha_inicio_str
            fecha_fin_seleccionada = fecha_fin_str
            id_tipo_nomina_seleccionado = id_tipo_nomina_str

            if not id_tipo_nomina_str or not fecha_inicio_str or not fecha_fin_str:
                flash('Debe seleccionar un tipo de nómina, fecha de inicio y fecha de fin.', 'danger')
                # En caso de error, volvemos a renderizar con los datos para que no se pierdan
                nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
                return render_template(
                    'generar_nomina.html', 
                    nominas=nominas, 
                    tipos_nomina=tipos_nomina,
                    fecha_inicio_seleccionada=fecha_inicio_seleccionada,
                    fecha_fin_seleccionada=fecha_fin_seleccionada,
                    id_tipo_nomina_seleccionado=id_tipo_nomina_seleccionado
                )

            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            id_tipo_nomina = int(id_tipo_nomina_str)
            
            tipo_nomina_seleccionado = TipoNomina.query.get(id_tipo_nomina)
            if not tipo_nomina_seleccionado:
                flash('Tipo de nómina no encontrado.', 'danger')
                nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
                return render_template(
                    'generar_nomina.html', 
                    nominas=nominas, 
                    tipos_nomina=tipos_nomina,
                    fecha_inicio_seleccionada=fecha_inicio_seleccionada,
                    fecha_fin_seleccionada=fecha_fin_seleccionada,
                    id_tipo_nomina_seleccionado=id_tipo_nomina_seleccionado
                )


            empleados = Empleado.query.filter_by(TipoNomina_id_tipo_nomina=id_tipo_nomina).all()
            
            if not empleados:
                flash('No se encontraron empleados para el tipo de nómina seleccionado.', 'warning')
                nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
                return render_template(
                    'generar_nomina.html', 
                    nominas=nominas, 
                    tipos_nomina=tipos_nomina,
                    fecha_inicio_seleccionada=fecha_inicio_seleccionada,
                    fecha_fin_seleccionada=fecha_fin_seleccionada,
                    id_tipo_nomina_seleccionado=id_tipo_nomina_seleccionado
                )
                
            nominas_generadas_info = []

            for empleado in empleados:
                # ... (resto de tu lógica de cálculo de nómina) ...
                monto_por_asistencia = db.session.query(func.sum(RegistroAsistencia.monto_pago)).filter(
                    RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                    RegistroAsistencia.fecha_registro.between(fecha_inicio, fecha_fin),
                    RegistroAsistencia.aprobacion_registro == True 
                ).scalar() or 0.0

                acciones_personales = Accion_Personal.query.filter(
                    Accion_Personal.Empleado_id_empleado == empleado.id_empleado,
                    Accion_Personal.fecha_aprobacion.isnot(None)
                ).all()
                
                dias_compensados = 0
                HORAS_NOMINALES_DIA = 8.0 
                horas_mensuales = 48 * HORAS_NOMINALES_DIA 
                costo_por_hora_normal_base = empleado.salario_base / horas_mensuales if horas_mensuales else 0.0

                for ap in acciones_personales:
                    tipo_ap = Tipo_AP.query.get(ap.Tipo_Ap_id_tipo_ap) 
                    if tipo_ap and tipo_ap.nombre_tipo.lower() in ['vacaciones', 'incapacidad']:
                        if ap.fecha_inicio and ap.fecha_fin:
                            inicio_ap_periodo = max(ap.fecha_inicio, fecha_inicio)
                            fin_ap_periodo = min(ap.fecha_fin, fecha_fin)
                            
                            if fin_ap_periodo >= inicio_ap_periodo:
                                dias_compensados += (fin_ap_periodo - inicio_ap_periodo).days + 1
                
                monto_por_vac_incap = dias_compensados * HORAS_NOMINALES_DIA * costo_por_hora_normal_base
                
                total_monto_bruto = monto_por_asistencia + monto_por_vac_incap

                if total_monto_bruto == 0:
                    nominas_generadas_info.append(f"Advertencia: Para {empleado.nombre_completo}, no se encontraron registros de asistencia aprobados ni días de vacaciones/incapacidad en el período. Nómina no generada para este empleado.")
                    continue 

                total_deducciones_calculadas = 0.0

                PORCENTAJE_CCSS_SEM = 0.0550 
                PORCENTAJE_CCSS_IVM = 0.0417  
                PORCENTAJE_LPT = 0.0100     
                
                deduccion_sem = total_monto_bruto * PORCENTAJE_CCSS_SEM
                deduccion_ivm = total_monto_bruto * PORCENTAJE_CCSS_IVM
                deduccion_lpt = total_monto_bruto * PORCENTAJE_LPT

                total_deducciones_calculadas += deduccion_sem
                total_deducciones_calculadas += deduccion_ivm
                total_deducciones_calculadas += deduccion_lpt

                BASE_SALARIO_EXENTO_ISR = 922000.00
                TRAMO_1 = {'limite': 1352000.00, 'porcentaje': 0.10}
                TRAMO_2 = {'limite': 2373000.00, 'porcentaje': 0.15}
                TRAMO_3 = {'limite': 4745000.00, 'porcentaje': 0.20}
                TRAMO_4 = {'limite': float('inf'), 'porcentaje': 0.25} 

                tramos_isr = [TRAMO_1, TRAMO_2, TRAMO_3, TRAMO_4]
                
                dias_del_periodo = (fecha_fin - fecha_inicio).days + 1
                factor_prorrateo = dias_del_periodo / 30.4167 

                salario_exento_isr = BASE_SALARIO_EXENTO_ISR * factor_prorrateo

                deduccion_isr = 0.0
                salario_a_gravar = total_monto_bruto - salario_exento_isr

                if salario_a_gravar > 0:
                    monto_anterior_tramo = 0.0
                    for tramo in tramos_isr:
                        limite_prorrateado = tramo['limite'] * factor_prorrateo
                        monto_en_tramo = min(salario_a_gravar, limite_prorrateado - monto_anterior_tramo)
                        
                        if monto_en_tramo > 0:
                            deduccion_isr += monto_en_tramo * tramo['porcentaje']
                            salario_a_gravar -= monto_en_tramo
                        
                        monto_anterior_tramo = limite_prorrateado
                        
                        if salario_a_gravar <= 0:
                            break 
                
                total_deducciones_calculadas += deduccion_isr

                monto_neto = total_monto_bruto - total_deducciones_calculadas
                
                nueva_nomina = Nomina(
                    Empleado_id_empleado=empleado.id_empleado,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    salario_bruto=round(total_monto_bruto, 2),
                    salario_neto=round(monto_neto, 2),
                    deducciones=round(total_deducciones_calculadas, 2), 
                    TipoNomina_id_tipo_nomina=id_tipo_nomina,
                    fecha_creacion=datetime.now()
                )
                db.session.add(nueva_nomina)
                nominas_generadas_info.append(f"Nómina generada para {empleado.nombre_completo} (Bruto: {total_monto_bruto:.2f}, Deducciones: {total_deducciones_calculadas:.2f}, Neto: {monto_neto:.2f}).")
            
            db.session.commit()
            flash('Nómina generada y guardada exitosamente.', 'success')
            for msg in nominas_generadas_info:
                flash(msg, 'info')
            
            # *** CAMBIO CLAVE AQUI: REDIRECCIONAR DESPUÉS DE UN POST EXITOSO ***
            return redirect(url_for('registro_asistencia.generar_nomina')) 


        except Exception as e:
            db.session.rollback()
            logging.error(f"Error al generar la nómina: {str(e)}", exc_info=True)
            flash(f'Ocurrió un error al generar la nómina. Por favor, intente de nuevo. (Detalle: {str(e)})', 'danger')
            # Si hay un error, aún renderizamos la página directamente con los valores del formulario
            nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
            return render_template(
                'generar_nomina.html', 
                nominas=nominas, 
                tipos_nomina=tipos_nomina,
                fecha_inicio_seleccionada=fecha_inicio_seleccionada,
                fecha_fin_seleccionada=fecha_fin_seleccionada,
                id_tipo_nomina_seleccionado=id_tipo_nomina_seleccionado
            )

    # Este bloque maneja las solicitudes GET (carga inicial o después de un redirect)
    nominas = Nomina.query.order_by(Nomina.fecha_creacion.desc()).all()
    return render_template(
        'generar_nomina.html', 
        nominas=nominas, 
        tipos_nomina=tipos_nomina,
        # En la carga GET, estos serán None, o los valores de flashed messages si se implementan
        fecha_inicio_seleccionada=None, 
        fecha_fin_seleccionada=None,
        id_tipo_nomina_seleccionado=None
    )



# -----------------------------------------------------------------------------------------------        

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
    
    
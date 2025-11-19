from flask import Blueprint, logging, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from payroll_app.routes.decorators import permiso_requerido
from sqlalchemy import func
from payroll_app.models import db, RegistroAsistencia, Feriado, Empleado, Nomina, TipoNomina, Tipo_AP, Accion_Personal
from datetime import datetime, date, time, timedelta
import os, logging
from werkzeug.utils import secure_filename # Importar para nombres de archivo seguros
from sqlalchemy.orm import joinedload
from payroll_app.utils import cargar_configuracion

""" Blueprint para el módulo de Registro de Asistencia """
registro_asistencia_bp = Blueprint('registro_asistencia', __name__)

""" Configuración de carga de archivos """
UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads'))
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

""" Define las extensiones permitidas para los archivos subidos """
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    """Función para validar la extensión del archivo."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

PER_PAGE = 10 # Número de registros por página 

""" Rutas y lógica para el módulo de Registro de Asistencia"""
@registro_asistencia_bp.route('/procesar_aprobacion', methods=['POST'])
@login_required
@permiso_requerido('listar_asistencia')
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

""" Vista para aprobar horas extras """
@registro_asistencia_bp.route('/aprobar_horas_extras')
@permiso_requerido('listar_asistencia')
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

""" Vista principal de registro de asistencia """
@registro_asistencia_bp.route('/asistencia', methods=['GET'])
@login_required
def ver_asistencia():
    empleado = Empleado.query.filter_by(Usuario_id_usuario=current_user.id_usuario).first()
    if not empleado:
        flash('Error de autenticación: No se encontró el empleado asociado a tu cuenta. Contacta al administrador.', 'danger')
        return redirect(url_for('auth.base')) 

    ahora = datetime.now()
    fecha_hoy = ahora.date()

    # --- Lógica para determinar el estado del botón ---
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
            #print(f"DEBUG (ver_asistencia): Estado determinado: '{estado_actual}' (No ha marcado salida a almuerzo).")
        elif registro_activo.hora_entrada_almuerzo and not registro_activo.hora_salida_almuerzo:
            estado_actual = 'regreso_almuerzo' 
            #print(f"DEBUG (ver_asistencia): Estado determinado: '{estado_actual}' (Salió a almorzar, aún no regresó).")
        elif registro_activo.hora_entrada_almuerzo and registro_activo.hora_salida_almuerzo and not registro_activo.hora_salida:
            estado_actual = 'salida_final' 
            #print(f"DEBUG (ver_asistencia): Estado determinado: '{estado_actual}' (Regresó del almuerzo, aún no finalizó).")
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

    return render_template('asistencia/registro_asistencia.html', 
                           estado_actual=estado_actual,
                           registros=registros_asistencia_display)

""" Acción para registrar la asistencia """
@registro_asistencia_bp.route('/asistencia/registrar', methods=['POST'])
@login_required 
def registrar_asistencia():
    # Carga configuracion de variablaes
    CONFIG = cargar_configuracion()
    # Configuracion de variables en configuracion
    MIN_TIEMPO_ENTRE_MARCAS = CONFIG.get('MIN_TIEMPO_ENTRE_MARCAS', timedelta(minutes=1))
    JORNADA_MINIMA_PAUSA_OBLIGATORIA = CONFIG.get('JORNADA_MINIMA_PAUSA_OBLIGATORIA', timedelta(hours=6))
    MIN_DURACION_JORNADA = CONFIG.get('MIN_DURACION_JORNADA', timedelta(minutes=30))
    HORAS_POR_JORNADA_NORMAL = CONFIG.get('HORAS_POR_JORNADA_NORMAL', 8.0)
    HORAS_MES_ESTANDAR = CONFIG.get('HORAS_MES_ESTANDAR', 208.0)
    HORAS_QUINCENA_ESTANDAR = CONFIG.get('HORAS_QUINCENA_ESTANDAR', 96.0)
    HORAS_SEMANA_ESTANDAR = CONFIG.get('HORAS_SEMANA_ESTANDAR', 48.0)
    # Obtener el empleado asociado al usuario actual
    empleado = Empleado.query.filter_by(Usuario_id_usuario=current_user.id_usuario).first()
    # Validar que el empleado exista
    if not empleado:
        flash('Error de autenticación: No se encontró el empleado asociado a tu cuenta.' \
        ' Contacta al administrador.', 'danger')
        return redirect(url_for('registro_asistencia.ver_asistencia'))
    # Obtener la fecha y hora actual
    ahora = datetime.now()
    fecha_registro = ahora.date()
    hora_registro = ahora.time()
    accion = request.form.get('accion')

    try:
        # --- Lógica para 'entrada' ---
        if accion == 'entrada':
            # Verificar si ya hay un entrada sin salida para hoy
            registro_incompleto_hoy = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.fecha_registro == fecha_registro,
                RegistroAsistencia.hora_salida.is_(None)
            ).first()
            # Si ya hay un registro incompleto hoy, no permitir nueva entrada
            if registro_incompleto_hoy:
                flash('Ya tienes una jornada activa para hoy. Si necesitas marcar una pausa o finalizar,' \
                ' usa el botón correspondiente.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))
            # Verificar si hay un registro incompleto de días anteriores
            registro_incompleto_anterior = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.fecha_registro < fecha_registro,
                RegistroAsistencia.hora_salida.is_(None)
            ).first()
            if registro_incompleto_anterior:
                flash(f'Advertencia: Tienes una jornada sin finalizar \
                       del día {registro_incompleto_anterior.fecha_registro.strftime("%d/%m/%Y")}. Por favor, \
                       contacta al administrador para resolverlo. Registrando tu entrada de hoy.', 'warning')
            # Verificar si ya finalizó la jornada hoy
            registro_finalizado_hoy = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.fecha_registro == fecha_registro,
                RegistroAsistencia.hora_salida.isnot(None)
            ).first()
            if registro_finalizado_hoy:
                flash('Ya has completado tu jornada de hoy. No se permite más de una entrada por día.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))
            # Crear un nuevo registro de asistencia
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=fecha_registro).first()
            feriado_id = es_feriado_hoy.id_feriado if es_feriado_hoy else None
            nuevo_registro = RegistroAsistencia(
                Empleado_id_empleado=empleado.id_empleado,
                fecha_registro=fecha_registro,
                hora_entrada=hora_registro,
                Feriado_id_feriado=feriado_id,
                aprobacion_registro=False,
                hora_entrada_almuerzo=None,
                hora_salida_almuerzo=None,
                total_horas=0.0,
                hora_extra=0.0,
                hora_feriado=0.0,
                monto_pago=0.0
            )
            db.session.add(nuevo_registro)
            db.session.commit()
            flash('¡Entrada registrada exitosamente! Tu jornada ha comenzado.', 'success')

        # --- Lógica para 'salida_almuerzo' (INICIO de la pausa) ---
        elif accion == 'salida_almuerzo':
            registro_activo = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.fecha_registro == fecha_registro,
                RegistroAsistencia.hora_entrada.isnot(None),
                RegistroAsistencia.hora_salida.is_(None),
                RegistroAsistencia.hora_salida_almuerzo.is_(None) # <-- Usar hora_salida_almuerzo (INICIO de pausa)
            ).first()
            # Validar tiempo mínimo desde la entrada
            if registro_activo:
                dt_entrada = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada)
                if ahora - dt_entrada < MIN_TIEMPO_ENTRE_MARCAS:
                    flash(f'No puedes marcar la salida al almuerzo tan pronto después \
                           de la entrada (mínimo {int(MIN_TIEMPO_ENTRE_MARCAS.total_seconds() / 60)} minuto).', 'warning')
                    return redirect(url_for('registro_asistencia.ver_asistencia'))
                registro_activo.hora_salida_almuerzo = hora_registro
                db.session.commit()
                flash('¡Salida para el almuerzo registrada!', 'info')
            else:
                flash('No puedes marcar la salida al almuerzo. Asegúrate de haber iniciado tu jornada y no haber marcado' \
                ' ya el almuerzo.', 'warning')

        # --- Lógica para 'regreso_almuerzo' (FIN de la pausa) ---
        elif accion == 'regreso_almuerzo':
            registro_activo = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.fecha_registro == fecha_registro,
                RegistroAsistencia.hora_entrada.isnot(None),
                RegistroAsistencia.hora_salida.is_(None),
                RegistroAsistencia.hora_salida_almuerzo.isnot(None),  # <-- Debe haber marcado salida (INICIO)
                RegistroAsistencia.hora_entrada_almuerzo.is_(None)    # <-- No debe haber marcado ya el regreso (FIN)
            ).first()
            # Validar tiempo mínimo desde la salida al almuerzo
            if registro_activo:
                # Usamos la hora de SALIDA al almuerzo (INICIO de pausa) para la validación de tiempo mínimo
                dt_salida_almuerzo = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_salida_almuerzo)
                # Usar MIN_TIEMPO_ENTRE_MARCAS como duración mínima del almuerzo
                if ahora < dt_salida_almuerzo + MIN_TIEMPO_ENTRE_MARCAS:
                    flash(f'La hora de regreso del almuerzo no puede ser anterior o demasiado cercana a la hora de salida (mínimo {int(MIN_TIEMPO_ENTRE_MARCAS.total_seconds() / 60)} minuto).', 'warning')
                    return redirect(url_for('registro_asistencia.ver_asistencia'))
                registro_activo.hora_entrada_almuerzo = hora_registro
                db.session.commit()
                flash('¡Regreso del almuerzo registrado!', 'info')
            else:
                flash('No puedes marcar el regreso del almuerzo. Asegúrate de haber marcado la salida al almuerzo y de tener una jornada activa.', 'warning')

        # --- Lógica para 'salida_final' ---
        elif accion == 'salida_final':
            # ... (Lógica de búsqueda y validación inicial se mantiene igual) ...
            registro_activo = RegistroAsistencia.query.filter(
                RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
                RegistroAsistencia.hora_salida.is_(None),
                RegistroAsistencia.fecha_registro.in_([fecha_registro, fecha_registro - timedelta(days=1)])
            ).first()
            # Validar que exista un registro activo
            if not registro_activo:
                flash('No hay una entrada de jornada activa para registrar la salida. Por favor, asegúrate de haber' \
                ' marcado tu entrada.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))
            # Validación de tiempo mínimo desde la entrada
            dt_entrada = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada)
            dt_salida_actual_temp = datetime.combine(fecha_registro, hora_registro)
            # Ajuste si la salida es antes de la entrada (cruce de medianoche)
            if dt_salida_actual_temp < dt_entrada:
                dt_salida_actual_temp += timedelta(days=1)
            # Validación de duración mínima de jornada
            if dt_salida_actual_temp - dt_entrada < MIN_DURACION_JORNADA:
                flash(f'No puedes registrar una salida final en menos \
                       de {int(MIN_DURACION_JORNADA.total_seconds() / 60)} minutos desde tu entrada.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))
            # Validación de regreso de almuerzo (si marcó salida a almuerzo)
            # Debe haber marcado INICIO de pausa (hora_salida_almuerzo) pero no FIN de pausa (hora_entrada_almuerzo)
            if registro_activo.hora_salida_almuerzo and not registro_activo.hora_entrada_almuerzo:
                flash('Debes registrar el regreso del almuerzo antes de finalizar la jornada.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))

            registro_activo.hora_salida = hora_registro

            # --- CÁLCULO DE TIEMPOS DE JORNADA ---
            dt_entrada = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada)
            dt_salida = datetime.combine(fecha_registro, hora_registro)
            if dt_salida < dt_entrada:
                dt_salida += timedelta(days=1)
            total_time_bruto = dt_salida - dt_entrada

            pausa_real_almuerzo = timedelta(minutes=0)
            
            # Hora_salida_almuerzo es el INICIO de pausa, hora_entrada_almuerzo es el FIN de pausa
            if registro_activo.hora_entrada_almuerzo and registro_activo.hora_salida_almuerzo:
                dt_regreso_almuerzo = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_entrada_almuerzo) 
                dt_salida_almuerzo = datetime.combine(registro_activo.fecha_registro, registro_activo.hora_salida_almuerzo)     
                # Ajuste si el almuerzo pasó la medianoche
                if dt_regreso_almuerzo < dt_salida_almuerzo:
                    dt_regreso_almuerzo += timedelta(days=1)
                pausa_real_almuerzo = dt_regreso_almuerzo - dt_salida_almuerzo
            total_time_neto = total_time_bruto
            # Restar la pausa de almuerzo si existe
            if pausa_real_almuerzo > timedelta(minutes=0):
                total_time_neto -= pausa_real_almuerzo
            elif total_time_bruto > JORNADA_MINIMA_PAUSA_OBLIGATORIA:
                total_time_neto -= timedelta(minutes=60) 
            
            registro_activo.total_horas = round(total_time_neto.total_seconds() / 3600, 2)

            # --- VERIFICAR Feriado para el día de la ENTRADA ---
            es_feriado_hoy = Feriado.query.filter_by(fecha_feriado=registro_activo.fecha_registro).first()
            registro_activo.Feriado_id_feriado = es_feriado_hoy.id_feriado if es_feriado_hoy else None

            # --- CÁLCULO DEL COSTO POR HORA SEGÚN LA PERIODICIDAD DEL SALARIO ---
            costo_por_hora_normal = 0
            horas_periodo_calculo = 0

            if empleado.salario_base is not None and float(empleado.salario_base) > 0:
                if empleado.periodicidad_salario == 'MENSUAL':
                    horas_periodo_calculo = HORAS_MES_ESTANDAR
                elif empleado.periodicidad_salario == 'QUINCENAL':
                    horas_periodo_calculo = HORAS_QUINCENA_ESTANDAR
                elif empleado.periodicidad_salario == 'SEMANAL':
                    horas_periodo_calculo = HORAS_SEMANA_ESTANDAR
                else:
                    logging.warning(f"Periodicidad de salario inesperada para empleado {empleado.id_empleado}: {empleado.periodicidad_salario}. Asumiendo mensual estándar para cálculo de hora.")
                    horas_periodo_calculo = HORAS_MES_ESTANDAR

                if horas_periodo_calculo > 0:
                    costo_por_hora_normal = float(empleado.salario_base) / horas_periodo_calculo
                else:
                    logging.error(f"Horas de período de cálculo son cero para empleado {empleado.id_empleado} con periodicidad {empleado.periodicidad_salario}. No se pudo calcular costo_por_hora_normal. Asignando 0.")
                    costo_por_hora_normal = 0
            else:
                logging.warning(f"Salario base no definido o cero para empleado {empleado.id_empleado}. Monto de pago será 0.")
                costo_por_hora_normal = 0

            # --- CÁLCULO DE MONTO DE PAGO, HORAS EXTRA Y HORAS FERIADO ---
            costo_por_hora_extra = costo_por_hora_normal * 1.5
            costo_por_hora_feriado = costo_por_hora_normal * 2

            registro_activo.hora_extra = 0.0
            registro_activo.hora_feriado = 0.0
            monto_pago_calculado = 0.0

            if es_feriado_hoy and es_feriado_hoy.pago_obligatorio:
                registro_activo.hora_feriado = registro_activo.total_horas
                monto_pago_calculado = registro_activo.total_horas * costo_por_hora_feriado
            else:
                horas_nominales_trabajadas = min(registro_activo.total_horas, HORAS_POR_JORNADA_NORMAL)
                registro_activo.hora_extra = max(0, registro_activo.total_horas - HORAS_POR_JORNADA_NORMAL)
                
                monto_pago_calculado = (horas_nominales_trabajadas * costo_por_hora_normal) + \
                                       (registro_activo.hora_extra * costo_por_hora_extra)

            registro_activo.monto_pago = round(monto_pago_calculado, 2)

            # Lógica de aprobación
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
        logging.exception(f"Error al registrar la asistencia para empleado {empleado.id_empleado}.") 
        flash(f'Ocurrió un error al registrar la asistencia. Por favor, inténtelo de nuevo. Detalle: {str(e)}', 'danger')
    
    return redirect(url_for('registro_asistencia.ver_asistencia'))

""" --------------------------------------------------------------------------------------
    RUTAS DE MANTENIMIENTO DE REGISTRO DE ASISTENCIA"""
""" Vista para listar registros de asistencia ------------------------------------------------"""
@registro_asistencia_bp.route('/listar_asistencia')
@permiso_requerido('listar_asistencia')
@login_required
def listar_asistencia():
    # 1. Parámetros de paginación y filtros
    page = request.args.get('page', 1, type=int)
    fecha_inicio_filtro = request.args.get('fecha_inicio')
    fecha_fin_filtro = request.args.get('fecha_fin')
    empleado_id_filtro = request.args.get('empleado_id') # Viene como string (o 'all' o None)
    aprobacion_filtro = request.args.get('aprobacion') # Viene como string ('approved', 'pending', 'all')
    # Base de la consulta, incluyendo la carga de empleado y tipo_nomina
    # Esto es importante para mostrar la información del empleado en la lista
    query = RegistroAsistencia.query \
        .options(joinedload(RegistroAsistencia.empleado).joinedload(Empleado.tipo_nomina_relacion)) \
        .order_by(RegistroAsistencia.fecha_registro.desc())
    # 2. Aplicar filtros
    if fecha_inicio_filtro:
        try:
            query = query.filter(RegistroAsistencia.fecha_registro >= datetime.strptime(fecha_inicio_filtro, '%Y-%m-%d').date())
        except ValueError:
            flash('Formato de fecha de inicio inválido para el filtro.', 'danger')
            fecha_inicio_filtro = None # Resetear el filtro si es inválido
    
    if fecha_fin_filtro:
        try:
            query = query.filter(RegistroAsistencia.fecha_registro <= datetime.strptime(fecha_fin_filtro, '%Y-%m-%d').date())
        except ValueError:
            flash('Formato de fecha de fin inválido para el filtro.', 'danger')
            fecha_fin_filtro = None # Resetear el filtro si es inválido
    
    if empleado_id_filtro and empleado_id_filtro != 'all':
        try:
            empleado_id_int = int(empleado_id_filtro)
            query = query.filter(RegistroAsistencia.Empleado_id_empleado == empleado_id_int)
        except ValueError:
            flash('ID de empleado inválido para el filtro.', 'danger')
            empleado_id_filtro = 'all' # Resetear el filtro si es inválido
    
    if aprobacion_filtro and aprobacion_filtro != 'all':
        is_approved = aprobacion_filtro == 'approved'
        query = query.filter(RegistroAsistencia.aprobacion_registro == is_approved)

    # 3. Paginación de los resultados
    registros = query.paginate(page=page, per_page=PER_PAGE, error_out=False)

    # 4. Obtener todos los empleados para el filtro del select en la plantilla
    todos_empleados = Empleado.query.order_by(Empleado.nombre).all()
    
    # 5. Renderizar la plantilla, pasando todos los filtros y el objeto de paginación
    return render_template('asistencia/listar_asistencia.html',
                           registros=registros, # Objeto de paginación (contiene .items, .has_next, etc.)
                           todos_empleados=todos_empleados,
                           fecha_inicio_filtro=fecha_inicio_filtro,
                           fecha_fin_filtro=fecha_fin_filtro,
                           empleado_id_filtro=empleado_id_filtro, # Pasar el string original para el select
                           aprobacion_filtro=aprobacion_filtro)

""" Funciones auxiliares para manejo de tiempos y cálculos """
def _parse_time_or_none(time_str):
    """Convierte un string 'HH:MM:SS' a datetime.time, manejando None o string vacío."""
    if time_str and time_str.strip():
        try:
            return datetime.strptime(time_str.strip(), '%H:%M:%S').time()
        except ValueError:
            # Si el formato es incorrecto, devolvemos None; el bloque principal lo manejará.
            return None
    return None

""" Funciones auxiliares para manejo de empleados y tipos de nómina """
def _get_empleado_with_nomina(empleado_id):
    """Obtiene un empleado con su tipo de nómina relacionado, incluyendo el TipoNomina."""
    # Asegúrate de que 'Empleado' y 'joinedload' estén correctamente importados
    return Empleado.query.options(joinedload(Empleado.tipo_nomina_relacion)).get(empleado_id) 

""" Función para calcular monto, horas extra y horas feriado """
def _calculate_monto(registro, empleado, costo_hora_normal):
    """Calcula el monto de pago, horas extra y horas feriado."""
    CONFIG = cargar_configuracion()
    HORAS_POR_JORNADA_NORMAL = CONFIG.get('HORAS_POR_JORNADA_NORMAL', 8.0)

    registro.hora_extra = 0.0
    registro.hora_feriado = 0.0
    monto_pago_calculado = 0.0

    if registro.total_horas == 0.0 or costo_hora_normal == 0:
        registro.monto_pago = 0.0
        return
        
    es_feriado = Feriado.query.filter_by(fecha_feriado=registro.fecha_registro).first()
    registro.Feriado_id_feriado = es_feriado.id_feriado if es_feriado else None
    
    costo_por_hora_extra = costo_hora_normal * 1.5
    costo_por_hora_feriado = costo_hora_normal * 2

    if es_feriado and es_feriado.pago_obligatorio:
        registro.hora_feriado = registro.total_horas
        monto_pago_calculado = registro.total_horas * costo_por_hora_feriado
    else:
        horas_nominales_trabajadas = min(registro.total_horas, HORAS_POR_JORNADA_NORMAL)
        registro.hora_extra = max(0, registro.total_horas - HORAS_POR_JORNADA_NORMAL)
        
        monto_pago_calculado = (horas_nominales_trabajadas * costo_hora_normal) + \
                                 (registro.hora_extra * costo_por_hora_extra)
    
    registro.monto_pago = round(monto_pago_calculado, 2)

""" Vista para editar un registro de asistencia ------------------------------------------------"""
@registro_asistencia_bp.route('/editar/<int:registro_id>', methods=['GET', 'POST'])
@login_required
def editar_asistencia(registro_id):
    CONFIG = cargar_configuracion()

    HORAS_MES_ESTANDAR = CONFIG.get('HORAS_MES_ESTANDAR', 208.0)
    JORNADA_MINIMA_PAUSA_OBLIGATORIA = CONFIG.get('JORNADA_MINIMA_PAUSA_OBLIGATORIA', timedelta(hours=6))
    registro = RegistroAsistencia.query.get_or_404(registro_id)
    empleado = _get_empleado_with_nomina(registro.Empleado_id_empleado)

    if not empleado:
        flash('Error: No se encontró el empleado asociado al registro de asistencia.', 'danger')
        return redirect(url_for('registro_asistencia.listar_asistencia'))

    # Parámetros de la URL para la paginación y filtros
    page = request.args.get('page', 1, type=int)
    fecha_inicio_filtro = request.args.get('fecha_inicio')
    fecha_fin_filtro = request.args.get('fecha_fin')
    empleado_id_filtro = request.args.get('empleado_id') 
    aprobacion_filtro = request.args.get('aprobacion')

    # Diccionario para construir la redirección con todos los filtros
    redirect_params = {
        'page': page,
        'fecha_inicio': fecha_inicio_filtro,
        'fecha_fin': fecha_fin_filtro,
        'empleado_id': empleado_id_filtro,
        'aprobacion': aprobacion_filtro
    }

    if request.method == 'POST':
        try:
            # --- 1. Obtención y Saneamiento de Datos del Formulario (SIN CAMBIOS) ---
            # ... (Código 1, 2 y 3: Obtención de datos, validaciones y asignación al registro) ...
            nueva_fecha_registro = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
            aprobado_form = 'aprobado' in request.form
            
            nueva_hora_entrada = _parse_time_or_none(request.form.get('hora_entrada'))
            nueva_hora_salida = _parse_time_or_none(request.form.get('hora_salida'))
            
            hora_salida_almuerzo_form = _parse_time_or_none(request.form.get('hora_salida_almuerzo'))
            hora_regreso_almuerzo_form = _parse_time_or_none(request.form.get('hora_regreso_almuerzo'))
            
            if not nueva_hora_entrada:
                flash('Error: La hora de entrada es obligatoria.', 'danger')
                return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro_id, **redirect_params))
            
            if not empleado.salario_base or float(empleado.salario_base) <= 0:
                flash(f'Error: El salario base del empleado {empleado.nombre} no es válido. Actualice el perfil del empleado.', 'danger')
                return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro_id, **redirect_params))
                
            registro.fecha_registro = nueva_fecha_registro
            registro.hora_entrada = nueva_hora_entrada
            registro.hora_salida = nueva_hora_salida
            registro.hora_salida_almuerzo = hora_salida_almuerzo_form
            registro.hora_entrada_almuerzo = hora_regreso_almuerzo_form
            registro.aprobacion_registro = aprobado_form
            
            # --- 4. Lógica de Cálculo de Tiempos y Monto (BLOQUE CORREGIDO) ---
            if registro.hora_salida:
                
                # CÁLCULO UNIFICADO DEL COSTO POR HORA               
                costo_por_hora_normal = 0
                if HORAS_MES_ESTANDAR > 0:
                    costo_por_hora_normal = float(empleado.salario_base) / HORAS_MES_ESTANDAR

                # CÁLCULO DEL TIEMPO TRABAJADO (SIN CAMBIOS)
                dt_entrada = datetime.combine(nueva_fecha_registro, registro.hora_entrada)
                dt_salida = datetime.combine(nueva_fecha_registro, registro.hora_salida)

                if dt_salida < dt_entrada:
                    dt_salida += timedelta(days=1)

                total_time_bruto = dt_salida - dt_entrada
                
                if total_time_bruto < timedelta(minutes=0):
                    flash('Error: La hora de salida principal no puede ser anterior a la hora de entrada.','danger')
                    return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro_id, **redirect_params))

                pausa_real_almuerzo = timedelta(minutes=0)
                pausa_obligatoria_deducida = timedelta(minutes=0)
                
                # Si ambos campos de pausa están llenos en la DB, calcular la pausa real
                if registro.hora_salida_almuerzo and registro.hora_entrada_almuerzo:
                    dt_inicio_pausa_db = datetime.combine(nueva_fecha_registro, registro.hora_salida_almuerzo)
                    dt_fin_pausa_db = datetime.combine(nueva_fecha_registro, registro.hora_entrada_almuerzo)
                    
                    if dt_fin_pausa_db < dt_inicio_pausa_db:
                               dt_fin_pausa_db += timedelta(days=1)
                    
                    pausa_real_almuerzo = dt_fin_pausa_db - dt_inicio_pausa_db

                    if pausa_real_almuerzo < timedelta(minutes=0):
                        flash('Error: La hora de regreso del almuerzo no puede ser anterior a la de salida.','danger')
                        return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro_id, **redirect_params))
                
                else:
                    # Aplicar Pausa Obligatoria SOLO si NO se registró pausa real y la jornada es larga
                    if total_time_bruto > JORNADA_MINIMA_PAUSA_OBLIGATORIA:
                               pausa_obligatoria_deducida = timedelta(minutes=60)

                # Cálculo final del tiempo neto
                total_time_neto = total_time_bruto - pausa_real_almuerzo - pausa_obligatoria_deducida
                        
                if total_time_neto < timedelta(minutes=0):
                    total_time_neto = timedelta(minutes=0)

                registro.total_horas = round(total_time_neto.total_seconds() / 3600, 2)
                
                # CÁLCULO DEL MONTO FINAL (Ahora usa el costo_por_hora_normal CORRECTO)
                _calculate_monto(registro, empleado, costo_por_hora_normal)
                
            else: # No hay hora de salida, resetear campos
                registro.total_horas = 0.0
                registro.hora_extra = 0.0
                registro.hora_feriado = 0.0
                registro.monto_pago = 0.0

            db.session.commit()
            flash('Registro de asistencia actualizado exitosamente.', 'success')

            # ----------------------------------------------------------------------------------
            # --- Lógica de Paginación Inteligente para Redirección (SIN CAMBIOS) ---
            # ... (Código para redirección) ...
            query_check = RegistroAsistencia.query.order_by(RegistroAsistencia.fecha_registro.desc())
            
            if fecha_inicio_filtro:
                query_check = query_check.filter(RegistroAsistencia.fecha_registro >= datetime.strptime(fecha_inicio_filtro, '%Y-%m-%d').date())
            if fecha_fin_filtro:
                query_check = query_check.filter(RegistroAsistencia.fecha_registro <= datetime.strptime(fecha_fin_filtro, '%Y-%m-%d').date())
            
            # Convertir a INT para la comparación con el ID de la base de datos
            if empleado_id_filtro and empleado_id_filtro != 'all':
                try:
                    empleado_id_int = int(empleado_id_filtro)
                    query_check = query_check.filter(RegistroAsistencia.Empleado_id_empleado == empleado_id_int)
                except ValueError:
                    logging.warning(f"Filtro empleado_id_filtro no es un entero válido: {empleado_id_filtro}")

            if aprobacion_filtro and aprobacion_filtro != 'all':
                is_approved = aprobacion_filtro == 'approved'
                query_check = query_check.filter(RegistroAsistencia.aprobacion_registro == is_approved)
            
            total_items_filtered = query_check.count()
            
            # Usamos PER_PAGE, que debe estar definido como una constante global (e.g., 20)
            max_pages = (total_items_filtered + PER_PAGE - 1) // PER_PAGE if total_items_filtered > 0 else 1

            # Ajustar la página si la actual excede el nuevo máximo
            if redirect_params['page'] > max_pages:
                redirect_params['page'] = max_pages
            
            return redirect(url_for('registro_asistencia.listar_asistencia', **redirect_params))
            # ----------------------------------------------------------------------------------
        
        except ValueError as e:
            db.session.rollback()
            logging.exception(f"Error de formato al actualizar registro {registro_id}: {e}")
            flash(f'Ocurrió un error de formato. Revise que las horas tengan el formato HH:MM:SS.', 'danger')
            return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro_id, **redirect_params))
            
        except Exception as e:
            db.session.rollback()
            logging.exception(f"Error inesperado al actualizar el registro de asistencia {registro_id}: {e}")
            flash(f'Ocurrió un error inesperado al actualizar el registro: {str(e)}', 'danger')
            return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro_id, **redirect_params))
    
    # Si es GET, simplemente renderiza el formulario
    return render_template('asistencia/editar_asistencia.html',
                           registro=registro,
                           **redirect_params)

""" Función para eliminar un registro de asistencia ------------------------------------------------"""
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

"""" Vista para generar nóminas ------------------------------------------------"""

""" Constantes y tramos ISR """
@permiso_requerido('listar_nominas')
@login_required
def calcular_isr(monto_bruto_periodo, fecha_inicio_obj, fecha_fin_obj):
    """
    Calcula el Impuesto sobre la Renta (ISR) para un monto bruto dado
    y un período de nómina, ajustando los tramos mensuales.
    """
    CONFIG = cargar_configuracion()
    BASE_SALARIO_EXENTO_ISR = CONFIG.get('BASE_SALARIO_EXENTO_ISR', 922000.00)
    TRAMOS_ISR = CONFIG.get('TRAMOS_ISR', [])

    dias_del_periodo = (fecha_fin_obj - fecha_inicio_obj).days + 1
    dias_mes_fiscal = 30 
    
    factor_ajuste_dias = dias_del_periodo / dias_mes_fiscal 
    
    base_exenta_ajustada = BASE_SALARIO_EXENTO_ISR * factor_ajuste_dias
    
    monto_sujeto_a_impuesto = max(0, monto_bruto_periodo - base_exenta_ajustada)
    
    isr_calculado = 0.0
    limite_anterior_ajustado = base_exenta_ajustada
    
    for tramo in TRAMOS_ISR:
        limite_tramo_ajustado = tramo['limite'] * factor_ajuste_dias
        porcentaje_tramo = tramo['porcentaje']
        monto_en_este_tramo = min(monto_sujeto_a_impuesto, limite_tramo_ajustado - limite_anterior_ajustado)

        if monto_en_este_tramo > 0:
            isr_calculado += monto_en_este_tramo * porcentaje_tramo
        
        monto_sujeto_a_impuesto -= monto_en_este_tramo
        limite_anterior_ajustado = limite_tramo_ajustado

        if monto_sujeto_a_impuesto <= 0:
            break
            
    return round(isr_calculado, 2)

""" Vista de generar nóminas ------------------------------------------------"""
@registro_asistencia_bp.route('/generar_nomina', methods=['GET', 'POST'])
@permiso_requerido('listar_nominas')
@login_required
def generar_nomina():
    """
    Genera la nómina procesando asistencias, vacaciones, incapacidades y feriados,
    aplicando la lógica de la Ley de Costa Rica para incapacidades (días de carencia vs. subsidio).
    """
    CONFIG = cargar_configuracion()
    HORAS_MES_ESTANDAR = CONFIG.get('HORAS_MES_ESTANDAR', 208.0)
    HORAS_QUINCENA_ESTANDAR = CONFIG.get('HORAS_QUINCENA_ESTANDAR', 96.0)
    HORAS_SEMANA_ESTANDAR = CONFIG.get('HORAS_SEMANA_ESTANDAR', 48.0)
    HORAS_POR_JORNADA_NORMAL = CONFIG.get('HORAS_POR_JORNADA_NORMAL', 8.0)
    PORCENTAJE_CCSS_SEM = CONFIG.get('PORCENTAJE_CCSS_SEM', 0.0550)
    PORCENTAJE_CCSS_IVM = CONFIG.get('PORCENTAJE_CCSS_IVM', 0.0417)
    PORCENTAJE_LPT = CONFIG.get('PORCENTAJE_LPT', 0.0100)
    DIAS_DE_CARENCIA = CONFIG.get('DIAS_DE_CARENCIA', 3)
    FACTOR_PAGO_EMPLEADOR_INCAPACIDAD = CONFIG.get('FACTOR_PAGO_EMPLEADOR_INCAPACIDAD', 0.40)
    FACTOR_PAGO_EMPLEADOR_CARENCIA = CONFIG.get('FACTOR_PAGO_EMPLEADOR_CARENCIA', 0.50)

    tipos_nomina = TipoNomina.query.all()
    page = request.args.get('page', 1, type=int)
    per_page = 8 # Define cuántas nóminas listar por página

    fecha_inicio_str = request.form.get('fecha_inicio') or request.args.get('fecha_inicio')
    fecha_fin_str = request.form.get('fecha_fin') or request.args.get('fecha_fin')
    id_tipo_nomina_str = request.form.get('tipo_nomina_id') or request.args.get('tipo_nomina_id')

    fecha_inicio_obj, fecha_fin_obj, id_tipo_nomina_int = None, None, None
    fecha_inicio_seleccionada, fecha_fin_seleccionada, id_tipo_nomina_seleccionado = (
        fecha_inicio_str, fecha_fin_str, id_tipo_nomina_str
    )

    # Intento de conversión de fechas y ID
    if fecha_inicio_str:
        try:
            fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Formato de fecha de inicio inválido.', 'danger')
         
    if fecha_fin_str:
        try:
            fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Formato de fecha de fin inválido.', 'danger')
    # Intento de conversión de ID de tipo de nómina        
    if id_tipo_nomina_str:
        try:
            id_tipo_nomina_int = int(id_tipo_nomina_str)
        except ValueError:
            flash('Tipo de nómina inválido.', 'danger')

    # --- Lógica de filtrado y paginación para mostrar las nóminas existentes (GET) ---
    query = Nomina.query.order_by(Nomina.fecha_creacion.desc())
    # Aplicar filtros si existen
    if id_tipo_nomina_int:
        query = query.filter(Nomina.TipoNomina_id_tipo_nomina == id_tipo_nomina_int)

    if fecha_inicio_obj and fecha_fin_obj:
        query = query.filter(Nomina.fecha_inicio >= fecha_inicio_obj, Nomina.fecha_fin <= fecha_fin_obj)
    
    paginated_nominas = query.paginate(page=page, per_page=per_page, error_out=False)

    # --- INICIO DEL PROCESAMIENTO POST (GENERACIÓN) ---
    if request.method == 'POST':
        try:
            # Validaciones básicas
            if not all([id_tipo_nomina_int, fecha_inicio_obj, fecha_fin_obj]):
                flash('Debe seleccionar un tipo de nómina, fecha de inicio y fecha de fin.', 'danger')
                return redirect(url_for('registro_asistencia.generar_nomina'))
            # Validar que la fecha de inicio no sea posterior a la fecha de fin
            if fecha_inicio_obj > fecha_fin_obj:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'danger')
                return redirect(url_for('registro_asistencia.generar_nomina'))
            # Obtener el tipo de nómina seleccionado
            tipo_nomina = TipoNomina.query.get(id_tipo_nomina_int)
            if not tipo_nomina:
                flash('Tipo de nómina no encontrado.', 'danger')
                return redirect(url_for('registro_asistencia.generar_nomina'))
            
            # =========================================================================
            # LÓGICA DE VALIDACIÓN DEL RANGO DE FECHAS (Semanal/Quincenal/Mensual)
            # =========================================================================
            frecuencia = tipo_nomina.nombre_tipo.lower() 
            dias_periodo = (fecha_fin_obj - fecha_inicio_obj).days + 1
            es_valido = True
            mensaje_error = ""

            if frecuencia == 'semanal':
                # Exactamente 7 días
                if dias_periodo != 7:
                    es_valido = False
                    mensaje_error = f"La nómina debe ser **Semanal** (7 días). Periodo seleccionado: {dias_periodo} días."
            
            elif frecuencia == 'quincenal':
                # Rango de 14 a 16 días
                if dias_periodo < 14 or dias_periodo > 16:
                    es_valido = False
                    mensaje_error = f"La nómina debe ser **Quincenal** (14 a 16 días). Periodo seleccionado: {dias_periodo} días."

            elif frecuencia == 'mensual':
                # Rango de 28 a 31 días (para cubrir todos los meses)
                if dias_periodo < 28 or dias_periodo > 31:
                    es_valido = False
                    mensaje_error = f"La nómina debe ser **Mensual** (28 a 31 días). Periodo seleccionado: {dias_periodo} días."
            
            # Aplicar el resultado de la validación y detener el proceso si es inválido
            if not es_valido:
                flash(f" Error de Periodo para {tipo_nomina.nombre_tipo}: {mensaje_error}", 'danger')
                # Redirigir manteniendo los filtros
                return redirect(url_for('registro_asistencia.generar_nomina',
                                        fecha_inicio=fecha_inicio_seleccionada,
                                        fecha_fin=fecha_fin_seleccionada,
                                        tipo_nomina_id=id_tipo_nomina_seleccionado))
            # =========================================================================


            empleados_del_tipo_nomina = Empleado.query.filter_by(
                tipo_nomina_relacion=tipo_nomina
            ).order_by(Empleado.id_empleado).all()
            # Verificar si hay empleados para el tipo de nómina seleccionado
            if not empleados_del_tipo_nomina:
                flash('No se encontraron empleados para el tipo de nómina seleccionado.', 'warning')
                return redirect(url_for('registro_asistencia.generar_nomina'))

            nominas_generadas_info = []
            # Procesar cada empleado
            for empleado in empleados_del_tipo_nomina:
                
                # --- CALCULAR COSTO POR HORA BASE ---
                costo_por_hora_base = 0
                if empleado.salario_base is not None and float(empleado.salario_base) > 0:
                    periodicidad_nombre = empleado.tipo_nomina_relacion.nombre_tipo if empleado.tipo_nomina_relacion else None
                    horas_periodo_calculo_base = 0
                    # Asumiendo constantes HORAS_MES_ESTANDAR, HORAS_QUINCENA_ESTANDAR, HORAS_SEMANA_ESTANDAR
                    if periodicidad_nombre == 'Mensual':
                        horas_periodo_calculo_base = HORAS_MES_ESTANDAR 
                    elif periodicidad_nombre == 'Quincenal':
                        horas_periodo_calculo_base = HORAS_QUINCENA_ESTANDAR
                    elif periodicidad_nombre == 'Semanal':
                        horas_periodo_calculo_base = HORAS_SEMANA_ESTANDAR
                    
                    if horas_periodo_calculo_base > 0:
                        costo_por_hora_base = float(empleado.salario_base) / horas_periodo_calculo_base
                # ------------------------------------

                # 1. Verificar asistencia aprobada 
                has_asistencia = RegistroAsistencia.query.filter(
                    RegistroAsistencia.empleado == empleado,
                    RegistroAsistencia.fecha_registro.between(fecha_inicio_obj, fecha_fin_obj),
                    RegistroAsistencia.aprobacion_registro.is_(True)
                ).first()

                if not has_asistencia:
                    nominas_generadas_info.append(f"Advertencia: No se encontraron registros de asistencia aprobada para {empleado.nombre_completo}. Nómina no generada.")
                    continue
                
                # 2. Comprobar si ya existe una nómina 
                nomina_existente = Nomina.query.filter(
                    Nomina.empleado == empleado,
                    Nomina.fecha_inicio == fecha_inicio_obj,
                    Nomina.fecha_fin == fecha_fin_obj
                ).first()

                if nomina_existente:
                    nominas_generadas_info.append(f"Advertencia: Ya existe una nómina para {empleado.nombre_completo} en el período. Omitiendo.")
                    continue # Saltar a siguiente empleado

                # 3. Sumar el monto de pago de asistencias aprobadas
                monto_por_asistencia = db.session.query(func.sum(RegistroAsistencia.monto_pago)).filter(
                    RegistroAsistencia.empleado == empleado,
                    RegistroAsistencia.fecha_registro.between(fecha_inicio_obj, fecha_fin_obj),
                    RegistroAsistencia.aprobacion_registro.is_(True)
                ).scalar() or 0.0

                # 4. Y 5. CÁLCULO DE VACACIONES E INCAPACIDADES (LÓGICA CORREGIDA PARA CR)
                monto_por_vacaciones = 0.0          # Componente GRAVABLE (Salario)
                monto_por_incapacidad_subsidio = 0.0 # Componente NO GRAVABLE (40% Subsidio CCSS)
                monto_por_incapacidad_gravable = 0.0 # Componente GRAVABLE (Días de carencia)

                acciones_personales = Accion_Personal.query.filter(
                    Accion_Personal.empleado == empleado,
                    Accion_Personal.fecha_aprobacion.isnot(None),
                    Accion_Personal.fecha_inicio <= fecha_fin_obj,
                    Accion_Personal.fecha_fin >= fecha_inicio_obj,
                    Accion_Personal.tipo_ap.has(Tipo_AP.nombre_tipo.in_(['Vacaciones', 'Incapacidad']))
                ).all()

                for ap in acciones_personales:
                    inicio_ap_periodo = max(ap.fecha_inicio, fecha_inicio_obj)
                    fin_ap_periodo = min(ap.fecha_fin, fecha_fin_obj)
                    
                    if fin_ap_periodo >= inicio_ap_periodo:
                        
                        monto_diario_base = HORAS_POR_JORNADA_NORMAL * costo_por_hora_base

                        if ap.tipo_ap.nombre_tipo == 'Vacaciones':
                            dias_en_periodo = (fin_ap_periodo - inicio_ap_periodo).days + 1
                            monto_por_vacaciones += dias_en_periodo * monto_diario_base
                        
                        elif ap.tipo_ap.nombre_tipo == 'Incapacidad':
                            # LÓGICA CORREGIDA PARA MANEJAR DÍAS DE CARENCIA (1-3) y SUBSIDIO (4+)
                            dia_actual_incapacidad = inicio_ap_periodo
                            
                            while dia_actual_incapacidad <= fin_ap_periodo:
                                
                                # Número de día de la incapacidad (1, 2, 3, ...)
                                # Se calcula la diferencia de días desde el inicio real de la incapacidad.
                                dias_transcurridos_incapacidad = (dia_actual_incapacidad - ap.fecha_inicio).days
                                numero_dia = dias_transcurridos_incapacidad + 1 
                                
                                if numero_dia <= DIAS_DE_CARENCIA:
                                    # Días de Carencia (1-3): Pago directo del empleador, es GRAVABLE.
                                    monto_pago_carencia = monto_diario_base * FACTOR_PAGO_EMPLEADOR_CARENCIA
                                    monto_por_incapacidad_gravable += monto_pago_carencia
                                    
                                else:
                                    # Días 4 en adelante: 40% del subsidio, es NO GRAVABLE.
                                    monto_pago_subsidio_40 = monto_diario_base * FACTOR_PAGO_EMPLEADOR_INCAPACIDAD 
                                    monto_por_incapacidad_subsidio += monto_pago_subsidio_40
                                    
                                dia_actual_incapacidad += timedelta(days=1)


                # 6. Sumar el monto por feriados obligatorios no trabajados
                monto_feriados_no_trabajados = 0.0
                dia_actual = fecha_inicio_obj
                while dia_actual <= fecha_fin_obj:
                    es_feriado_obligatorio = Feriado.query.filter_by(fecha_feriado=dia_actual, pago_obligatorio=True).first()
                    if es_feriado_obligatorio:
                        registro_asistencia_aprobado = RegistroAsistencia.query.filter(
                            RegistroAsistencia.empleado == empleado,
                            RegistroAsistencia.fecha_registro == dia_actual,
                            RegistroAsistencia.aprobacion_registro.is_(True)
                        ).first()
                        if not registro_asistencia_aprobado:
                            monto_feriados_no_trabajados += HORAS_POR_JORNADA_NORMAL * costo_por_hora_base
                    dia_actual += timedelta(days=1)
                
                # 7. Calcular el monto bruto GRAVABLE (Salario sujeto a cargas sociales/ISR)
                monto_gravable_bruto = (
                    monto_por_asistencia + 
                    monto_por_vacaciones + 
                    monto_feriados_no_trabajados + 
                    monto_por_incapacidad_gravable # Días de carencia (Gravable)
                )

                # 8. Calcular el monto bruto TOTAL (Lo que se paga al empleado)
                total_monto_bruto = monto_gravable_bruto + monto_por_incapacidad_subsidio # Subsidio (No Gravable)

                # 9. Calcular deducciones y salario neto (Aplicadas SOLO a monto_gravable_bruto)
                # Asumiendo las constantes PORCENTAJE_CCSS_SEM, PORCENTAJE_CCSS_IVM, PORCENTAJE_LPT
                total_deducciones = (
                    monto_gravable_bruto * PORCENTAJE_CCSS_SEM +
                    monto_gravable_bruto * PORCENTAJE_CCSS_IVM +
                    monto_gravable_bruto * PORCENTAJE_LPT
                )
                # Asumiendo la función calcular_isr
                total_deducciones += calcular_isr(monto_gravable_bruto, fecha_inicio_obj, fecha_fin_obj)
                
                # 10. Salario neto final
                monto_neto = total_monto_bruto - total_deducciones

                # 11. Crear y guardar la nómina
                nueva_nomina = Nomina(
                    empleado=empleado,
                    fecha_inicio=fecha_inicio_obj,
                    fecha_fin=fecha_fin_obj,
                    salario_bruto=round(total_monto_bruto, 2),
                    salario_neto=round(monto_neto, 2),
                    deducciones=round(total_deducciones, 2),
                    tipo_nomina_relacion=tipo_nomina,
                    fecha_creacion=datetime.now()
                )
                db.session.add(nueva_nomina)
                nominas_generadas_info.append(f"Nómina generada para {empleado.nombre_completo}.")

            db.session.commit()
            
            # --- Manejo de mensajes Flash y Redirección ---
            nominas_exitosas = sum(1 for msg in nominas_generadas_info if "Nómina generada" in msg)
            nominas_advertencias = sum(1 for msg in nominas_generadas_info if "Advertencia" in msg)
            # Mostrar todos los mensajes generados
            for msg in nominas_generadas_info:
                categoria = 'warning' if "Advertencia" in msg else 'info' 
                flash(msg, categoria)
            # Resumen final
            if nominas_exitosas > 0 and nominas_advertencias == 0:
                flash(f'¡Éxito! Se generaron {nominas_exitosas} nóminas exitosamente.', 'success')
            # Advertencias presentes
            elif nominas_exitosas > 0 and nominas_advertencias > 0:
                flash(f'Proceso completado con advertencias. Se generaron {nominas_exitosas} nóminas, pero {nominas_advertencias} no se pudieron generar (ver detalles arriba).', 'warning')
            # Ninguna nómina generada
            elif nominas_exitosas == 0 and nominas_advertencias > 0:
                flash(f'Proceso completado, pero no se generó ninguna nómina (ver advertencias).', 'warning')
            # Ninguna nómina generada ni advertencias
            else:
                flash('Proceso finalizado. No se generaron nuevas nóminas.', 'info')

            return redirect(url_for('registro_asistencia.generar_nomina',
                fecha_inicio=fecha_inicio_seleccionada,
                fecha_fin=fecha_fin_seleccionada,
                tipo_nomina_id=id_tipo_nomina_seleccionado,
                page=page
            ))
        except Exception as e:
            db.session.rollback()
            logging.exception("Error al generar la nómina.")
            flash(f'Ocurrió un error al generar la nómina. Detalle: {str(e)}', 'danger')
            return redirect(url_for('registro_asistencia.generar_nomina',
                fecha_inicio=fecha_inicio_seleccionada,
                fecha_fin=fecha_fin_seleccionada,
                tipo_nomina_id=id_tipo_nomina_seleccionado,
                page=page
            ))

    # --- Manejo de la solicitud GET (Formulario Inicial) ---
    return render_template('nomina/generar_nomina.html', 
        tipos_nomina=tipos_nomina,
        paginated_nominas=paginated_nominas,
        fecha_inicio_seleccionada=fecha_inicio_seleccionada,
        fecha_fin_seleccionada=fecha_fin_seleccionada,
        id_tipo_nomina_seleccionado=id_tipo_nomina_seleccionado
    )
    
""" Vista para listar nóminas con paginación y filtros ------------------------------------------------"""
@registro_asistencia_bp.route('/listar_nominas')
@permiso_requerido('listar_nominas')
@login_required
def listar_nominas():
    """Muestra una lista de todas las nóminas generadas con paginación y filtros."""
    try:
        # 1. Obtener el número de página de la URL, por defecto es 1
        page = request.args.get('page', 1, type=int)
        
        # 2. Obtener los parámetros de filtro de la URL (para mantener el estado al paginar)
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        tipo_nomina_id_str = request.args.get('tipo_nomina_id')

        # Convertir a objetos de fecha e int si existen y son válidos
        fecha_inicio_obj = None
        fecha_fin_obj = None
        tipo_nomina_id_int = None

        if fecha_inicio_str:
            try:
                fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de fecha de inicio inválido para el filtro.', 'danger')

        if fecha_fin_str:
            try:
                fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de fecha de fin inválido para el filtro.', 'danger')
                
        if tipo_nomina_id_str:
            try:
                tipo_nomina_id_int = int(tipo_nomina_id_str)
            except ValueError:
                flash('Tipo de nómina inválido para el filtro.', 'danger')

        # Iniciar la consulta base
        query = Nomina.query.order_by(Nomina.fecha_creacion.desc())

        # Aplicar filtros si están presentes
        if fecha_inicio_obj:
            query = query.filter(Nomina.fecha_inicio >= fecha_inicio_obj)
        if fecha_fin_obj:
            query = query.filter(Nomina.fecha_fin <= fecha_fin_obj)
        if tipo_nomina_id_int:
            query = query.filter(Nomina.TipoNomina_id_tipo_nomina == tipo_nomina_id_int)

        # 3. y 4. Paginar los resultados y obtener el objeto Pagination
        # 'per_page' define cuántos ítems se mostrarán por página
        paginated_nominas = query.paginate(page=page, per_page=10, error_out=False)

        tipos_nomina = TipoNomina.query.all()
        
        return render_template(
            'nomina/generar_nomina.html',
            nominas=paginated_nominas.items,       # Los ítems (registros) de la página actual
            paginated_nominas=paginated_nominas,   # El objeto paginador completo para los controles
            tipos_nomina=tipos_nomina,
            # Pasar de vuelta los valores de filtro a la plantilla para mantener el estado del formulario
            fecha_inicio_seleccionada=fecha_inicio_str,
            fecha_fin_seleccionada=fecha_fin_str,
            id_tipo_nomina_seleccionado=tipo_nomina_id_str
        )
    except Exception as e:
        flash(f'Ocurrió un error al cargar las nóminas: {str(e)}', 'danger')
        tipos_nomina = TipoNomina.query.all()
        # En caso de error, devolver una lista vacía y un paginador nulo
        return render_template('nomina/generar_nomina.html', nominas=[], tipos_nomina=tipos_nomina, paginated_nominas=None)
    
""" Función para eliminar una nómina ------------------------------------------------"""
@registro_asistencia_bp.route('/nomina/eliminar/<int:id_nomina>', methods=['POST'])
@permiso_requerido('listar_nominas')
@login_required
def eliminar_nomina(id_nomina):

    nomina = Nomina.query.get_or_404(id_nomina) # Busca la nómina o devuelve un error 404 si no existe

    try:
        db.session.delete(nomina)
        db.session.commit()
        flash(f'Nómina eliminada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error al eliminar la nómina con ID {id_nomina}.")
        flash(f'Ocurrió un error al eliminar la nómina. Detalle: {str(e)}', 'danger')
    
    # Redirige a la página de generación de nóminas, manteniendo los filtros y la página si es posible
    # Esto requiere pasar los parámetros del request.args, si existen
    current_filters = {
        'fecha_inicio': request.args.get('fecha_inicio'),
        'fecha_fin': request.args.get('fecha_fin'),
        'tipo_nomina_id': request.args.get('tipo_nomina_id'),
        'page': request.args.get('page', 1)
    }
    # Elimina los None para no incluirlos en la URL
    current_filters = {k: v for k, v in current_filters.items() if v is not None}
    
    return redirect(url_for('registro_asistencia.generar_nomina', **current_filters))
from time import strptime
from flask import Blueprint, logging, render_template, request, flash, redirect, url_for, make_response
from flask_login import current_user, login_required
from payroll_app.routes.decorators import permiso_requerido
from sqlalchemy import func
from payroll_app.models import db, RegistroAsistencia, Feriado, Empleado, Nomina, TipoNomina, Tipo_AP, Accion_Personal, Deduccion, ConceptoNomina
from datetime import datetime, date, time, timedelta
import os, logging
from werkzeug.utils import secure_filename # Importar para nombres de archivo seguros
from sqlalchemy.orm import joinedload
from payroll_app.utils import cargar_configuracion
from payroll_app.pdf_utils import build_pdf_from_rows

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

def str_a_timedelta(time_str):
    """Convierte una cadena HH:MM:SS a un objeto timedelta."""
    if isinstance(time_str, timedelta):
        return time_str
    if not isinstance(time_str, str):
        # Si ya es un float, int o algo inesperado que no es str ni timedelta, devuelve 0 o maneja el error
        return timedelta(minutes=0) 
    
    try:
        parts = strptime(time_str, '%H:%M:%S')
        return timedelta(hours=parts.tm_hour, minutes=parts.tm_min, seconds=parts.tm_sec)
    except ValueError:
        # Maneja el caso en que el formato de la cadena sea incorrecto (ej: '30m' en lugar de '00:30:00')
        print(f"Advertencia: Formato de tiempo inválido en configuración: {time_str}")
        return timedelta(minutes=0) # Valor seguro por defecto

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
        
        # 1. ESTADO DE PAUSA (Acción que debe hacer el usuario: Regresar)
        # Se verifica: ¿Se marcó la SALIDA al almuerzo (INICIO) pero NO el REGRESO (FIN)?
        if registro_activo.hora_salida_almuerzo is not None and registro_activo.hora_entrada_almuerzo is None:
            estado_actual = 'regreso_almuerzo'
            # print("DEBUG: Estado determinado: 'regreso_almuerzo' (Está en pausa).")
            
        # 2. ESTADO INICIAL/POST-PAUSA (Acción que debe hacer el usuario: Salir al Almuerzo O Salir Final)
        # Se verifica: ¿Se marcó el REGRESO (FIN) O NO se ha marcado la SALIDA (INICIO)?
        
        elif registro_activo.hora_salida_almuerzo is None:
            # Solo hay entrada marcada (o la pausa fue borrada), la siguiente acción es Salir al Almuerzo.
            estado_actual = 'salida_almuerzo'
            # print("DEBUG: Estado determinado: 'salida_almuerzo' (Recién entró o necesita salir a almorzar).")
            
        elif registro_activo.hora_salida_almuerzo is not None and registro_activo.hora_entrada_almuerzo is not None:
            # Ambas marcas de almuerzo están llenas. La única opción restante es Salida Final.
            estado_actual = 'salida_final' 
            # print("DEBUG: Estado determinado: 'salida_final' (Almuerzo completo, listo para salir).")
            
        else:
            # Fallback si ninguna de las condiciones anteriores se cumple (debería ser 'salida_final')
            estado_actual = 'salida_final'
    else:
        # Si no hay un registro ACTIVO HOY, verificamos si ya FINALIZÓ su jornada HOY
        registro_finalizado_hoy = RegistroAsistencia.query.filter(
            RegistroAsistencia.Empleado_id_empleado == empleado.id_empleado,
            RegistroAsistencia.fecha_registro == fecha_hoy,
            RegistroAsistencia.hora_salida.isnot(None) # Busca un registro de hoy que ya finalizó
        ).first()
        
        if registro_finalizado_hoy:
            #print(f"DEBUG (ver_asistencia): Se encontró un registro FINALIZADO para HOY. Estado: 'jornada_completa_hoy'.")
            estado_actual = 'jornada_completa_hoy' 
            flash('Ya has completado tu jornada de hoy. No se permite más de una entrada por día.', 'info')
        else:
           # print(f"DEBUG (ver_asistencia): No se encontró ningún registro finalizado para HOY. Se asume estado: 'entrada'.")
            # Si no hay registro activo Y no hay registro finalizado, significa que el empleado puede marcar 'entrada'.
            estado_actual = 'entrada' 
    
    # Validación final para asegurar que el estado determinado sea uno de los conocidos por el JS
    estados_validos = ['entrada', 'salida_almuerzo', 'regreso_almuerzo', 'salida_final', 'jornada_completa_hoy']
    if estado_actual not in estados_validos:
        estado_actual = 'entrada' 

    #print(f"DEBUG (ver_asistencia): Estado actual FINAL que se envía al template: '{estado_actual}'") 

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
    MIN_TIEMPO_ENTRE_MARCAS = str_a_timedelta(CONFIG.get('MIN_TIEMPO_ENTRE_MARCAS', timedelta(minutes=1)))
    JORNADA_MINIMA_PAUSA_OBLIGATORIA = str_a_timedelta(CONFIG.get('JORNADA_MINIMA_PAUSA_OBLIGATORIA', timedelta(hours=6)))
    MIN_DURACION_JORNADA = str_a_timedelta(CONFIG.get('MIN_DURACION_JORNADA', timedelta(minutes=30)))
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
                if empleado.tipo_nomina_relacion == 'MENSUAL':
                    horas_periodo_calculo = HORAS_MES_ESTANDAR
                elif empleado.tipo_nomina_relacion == 'QUINCENAL':
                    horas_periodo_calculo = HORAS_QUINCENA_ESTANDAR
                elif empleado.tipo_nomina_relacion == 'SEMANAL':
                    horas_periodo_calculo = HORAS_SEMANA_ESTANDAR
                else:
                    logging.warning(f"Periodicidad de salario inesperada para empleado {empleado.id_empleado}: {empleado.tipo_nomina_relacion}. Asumiendo mensual estándar para cálculo de hora.")
                    horas_periodo_calculo = HORAS_MES_ESTANDAR

                if horas_periodo_calculo > 0:
                    costo_por_hora_normal = float(empleado.salario_base) / horas_periodo_calculo
                else:
                    logging.error(f"Horas de período de cálculo son cero para empleado {empleado.id_empleado} con periodicidad {empleado.tipo_nomina_relacion}. No se pudo calcular costo_por_hora_normal. Asignando 0.")
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
# Línea 517
def _calculate_monto(registro, empleado, costo_hora_normal):
    CONFIG = cargar_configuracion()
    HORAS_NORMALES_CONFIG = float(CONFIG.get('HORAS_POR_JORNADA_NORMAL', 8.0))

    # Limpiamos valores previos
    registro.hora_extra = 0.0
    registro.hora_feriado = 0.0
    
    # 1. DETECCIÓN SEGÚN TU REGLA (Domingo = 0)
    # Usamos .weekday() y comparamos contra 0
    es_domingo = (registro.fecha_registro.weekday() == 6)  # En Python, lunes=0, domingo=6. Ajustamos según tu regla.
    
    # 2. Verificación de feriados
    es_feriado = Feriado.query.filter_by(fecha_feriado=registro.fecha_registro).first()
    registro.Feriado_id_feriado = es_feriado.id_feriado if es_feriado else None

    # DEBUG: Para confirmar en consola si está detectando el 0 correctamente
    print(f"DEBUG: Fecha: {registro.fecha_registro}, Domingo (0)?: {es_domingo}, Total Horas: {registro.total_horas}")

    # 3. LÓGICA DE PAGO
    if es_feriado or es_domingo:
        # PAGO ESPECIAL (Domingo o Feriado)
        # Aquí NO se restan HORAS_NORMALES, todo se paga al doble (factor 2.0)
        registro.hora_feriado = registro.total_horas
        registro.hora_extra = 0.0
        monto_pago = registro.total_horas * (costo_hora_normal * 2.0)
    else:
        # PAGO NORMAL
        # Aquí SÍ se aplica el tope de 8 horas normales
        horas_normales_trabajadas = min(registro.total_horas, HORAS_NORMALES_CONFIG)
        registro.hora_extra = max(0, registro.total_horas - HORAS_NORMALES_CONFIG)
        
        monto_pago = (horas_normales_trabajadas * costo_hora_normal) + \
                     (registro.hora_extra * (costo_hora_normal * 1.5))
    
    registro.monto_pago = round(monto_pago, 2)

""" Vista para editar un registro de asistencia ------------------------------------------------"""
@registro_asistencia_bp.route('/asistencia/editar/<int:registro_id>', methods=['GET', 'POST'])
@login_required
def editar_asistencia(registro_id):
    CONFIG = cargar_configuracion()
    HORAS_MES_ESTANDAR = float(CONFIG.get('HORAS_MES_ESTANDAR', 208.0))
    PER_PAGE = CONFIG.get('PER_PAGE', 20)
    JORNADA_MINIMA_PAUSA_OBLIGATORIA = CONFIG.get('JORNADA_MINIMA_PAUSA_OBLIGATORIA', timedelta(hours=6))
    
    registro = RegistroAsistencia.query.get_or_404(registro_id)
    empleado = _get_empleado_with_nomina(registro.Empleado_id_empleado)

    if not empleado:
        flash('Error: No se encontró el empleado asociado al registro.', 'danger')
        return redirect(url_for('registro_asistencia.listar_asistencia'))

    redirect_params = {
        'page': request.args.get('page', 1, type=int),
        'fecha_inicio': request.args.get('fecha_inicio'),
        'fecha_fin': request.args.get('fecha_fin'),
        'empleado_id': request.args.get('empleado_id'),
        'aprobacion': request.args.get('aprobacion')
    }

    if request.method == 'POST':
        try:
            # 1. Actualización de datos básicos
            nueva_fecha = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
            registro.fecha_registro = nueva_fecha
            registro.aprobacion_registro = 'aprobado' in request.form
            registro.hora_entrada = _parse_time_or_none(request.form.get('hora_entrada'))
            registro.hora_salida = _parse_time_or_none(request.form.get('hora_salida'))
            
            if registro.hora_salida and registro.hora_entrada:
                costo_hora = float(empleado.salario_base) / HORAS_MES_ESTANDAR if HORAS_MES_ESTANDAR > 0 else 0
                
                # 2. Cálculo de tiempo bruto
                dt_ent = datetime.combine(nueva_fecha, registro.hora_entrada)
                dt_sal = datetime.combine(nueva_fecha, registro.hora_salida)
                if dt_sal < dt_ent: dt_sal += timedelta(days=1)
                total_bruto = dt_sal - dt_ent
                
                # 3. Cálculo de pausa
                pausa = timedelta(minutes=0)
                h_sal_alm = _parse_time_or_none(request.form.get('hora_salida_almuerzo'))
                h_reg_alm = _parse_time_or_none(request.form.get('hora_regreso_almuerzo'))
                
                if h_sal_alm and h_reg_alm:
                    dt_s_alm = datetime.combine(nueva_fecha, h_sal_alm)
                    dt_r_alm = datetime.combine(nueva_fecha, h_reg_alm)
                    if dt_r_alm < dt_s_alm: dt_r_alm += timedelta(days=1)
                    pausa = dt_r_alm - dt_s_alm
                elif total_bruto > JORNADA_MINIMA_PAUSA_OBLIGATORIA:
                    pausa = timedelta(minutes=60)
                
                registro.total_horas = round(max(timedelta(minutes=0), total_bruto - pausa).total_seconds() / 3600, 2)
                
                # 4. Cálculo de montos (Detecta automáticamente Domingo/Feriado)
                _calculate_monto(registro, empleado, costo_hora)
            else:
                # Resetear si no hay horas de salida
                registro.total_horas = registro.hora_extra = registro.hora_feriado = registro.monto_pago = 0.0

            db.session.commit()
            
            # 5. Paginación inteligente: recalcular límites tras el cambio
            query_check = RegistroAsistencia.query.order_by(RegistroAsistencia.fecha_registro.desc())
            # (Opcional: aquí podrías añadir los filtros de fecha/empleado si quieres una redirección más precisa)
            
            total_items = query_check.count()
            max_pages = (total_items + PER_PAGE - 1) // PER_PAGE if total_items > 0 else 1
            if redirect_params['page'] > max_pages: redirect_params['page'] = max_pages
            
            flash('Asistencia actualizada exitosamente.', 'success')
            return redirect(url_for('registro_asistencia.listar_asistencia', **redirect_params))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar: {str(e)}', 'danger')
            return redirect(url_for('registro_asistencia.editar_asistencia', registro_id=registro_id, **redirect_params))

    return render_template('asistencia/editar_asistencia.html', registro=registro, **redirect_params)

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

                # 9. Calcular deducciones por separado (Aplicadas SOLO a monto_gravable_bruto)
                # Asumiendo las constantes PORCENTAJE_CCSS_SEM, PORCENTAJE_CCSS_IVM, PORCENTAJE_LPT
                deduccion_ccss_sem = round(monto_gravable_bruto * PORCENTAJE_CCSS_SEM, 2)
                deduccion_ccss_ivm = round(monto_gravable_bruto * PORCENTAJE_CCSS_IVM, 2)
                deduccion_lpt = round(monto_gravable_bruto * PORCENTAJE_LPT, 2)
                deduccion_isr = round(calcular_isr(monto_gravable_bruto, fecha_inicio_obj, fecha_fin_obj), 2)
                
                # Total de deducciones
                total_deducciones = deduccion_ccss_sem + deduccion_ccss_ivm + deduccion_lpt + deduccion_isr
                
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
                db.session.flush()  # Guardar la nómina para obtener su ID
                
                # 12. Crear registros de deducción detallados
                if deduccion_ccss_sem > 0:
                    deduccion_record_sem = Deduccion(
                        Nomina_id_nomina=nueva_nomina.id_nomina,
                        tipo_deduccion='CCSS-SEM',
                        monto=deduccion_ccss_sem,
                        porcentaje=PORCENTAJE_CCSS_SEM * 100
                    )
                    db.session.add(deduccion_record_sem)
                
                if deduccion_ccss_ivm > 0:
                    deduccion_record_ivm = Deduccion(
                        Nomina_id_nomina=nueva_nomina.id_nomina,
                        tipo_deduccion='CCSS-IVM',
                        monto=deduccion_ccss_ivm,
                        porcentaje=PORCENTAJE_CCSS_IVM * 100
                    )
                    db.session.add(deduccion_record_ivm)
                
                if deduccion_lpt > 0:
                    deduccion_record_lpt = Deduccion(
                        Nomina_id_nomina=nueva_nomina.id_nomina,
                        tipo_deduccion='LPT',
                        monto=deduccion_lpt,
                        porcentaje=PORCENTAJE_LPT * 100
                    )
                    db.session.add(deduccion_record_lpt)
                
                if deduccion_isr > 0:
                    deduccion_record_isr = Deduccion(
                        Nomina_id_nomina=nueva_nomina.id_nomina,
                        tipo_deduccion='ISR',
                        monto=deduccion_isr,
                        porcentaje=None  # ISR no tiene un porcentaje fijo
                    )
                    db.session.add(deduccion_record_isr)
                
                # 13. Crear registros de conceptos (vacaciones, incapacidades)
                if monto_por_vacaciones > 0:
                    # Calcular días de vacaciones
                    monto_diario_base = HORAS_POR_JORNADA_NORMAL * costo_por_hora_base if costo_por_hora_base > 0 else 1
                    dias_vacaciones = int(round(monto_por_vacaciones / monto_diario_base)) if monto_diario_base > 0 else 0
                    
                    concepto_vacaciones = ConceptoNomina(
                        Nomina_id_nomina=nueva_nomina.id_nomina,
                        tipo_concepto='Vacaciones',
                        dias=dias_vacaciones,
                        monto=round(monto_por_vacaciones, 2),
                        descripcion='Días de vacaciones disfrutados'
                    )
                    db.session.add(concepto_vacaciones)
                
                if monto_por_incapacidad_gravable > 0:
                    # Incapacidad días de carencia (1-3 días, pago patrono 50%)
                    monto_diario_base = HORAS_POR_JORNADA_NORMAL * costo_por_hora_base if costo_por_hora_base > 0 else 1
                    dias_carencia = int(round(monto_por_incapacidad_gravable / (monto_diario_base * FACTOR_PAGO_EMPLEADOR_CARENCIA))) if (monto_diario_base * FACTOR_PAGO_EMPLEADOR_CARENCIA) > 0 else 0
                    
                    concepto_incapacidad_carencia = ConceptoNomina(
                        Nomina_id_nomina=nueva_nomina.id_nomina,
                        tipo_concepto='Incapacidad-Carencia',
                        dias=dias_carencia,
                        monto=round(monto_por_incapacidad_gravable, 2),
                        descripcion=f'Incapacidad: {dias_carencia} días de carencia (50% patrono)'
                    )
                    db.session.add(concepto_incapacidad_carencia)
                
                if monto_por_incapacidad_subsidio > 0:
                    # Incapacidad subsidio CAJA (4+ días, pago patrono 40%)
                    monto_diario_base = HORAS_POR_JORNADA_NORMAL * costo_por_hora_base if costo_por_hora_base > 0 else 1
                    dias_subsidio = int(round(monto_por_incapacidad_subsidio / (monto_diario_base * FACTOR_PAGO_EMPLEADOR_INCAPACIDAD))) if (monto_diario_base * FACTOR_PAGO_EMPLEADOR_INCAPACIDAD) > 0 else 0
                    
                    concepto_incapacidad_subsidio = ConceptoNomina(
                        Nomina_id_nomina=nueva_nomina.id_nomina,
                        tipo_concepto='Incapacidad-Subsidio',
                        dias=dias_subsidio,
                        monto=round(monto_por_incapacidad_subsidio, 2),
                        descripcion=f'Incapacidad: {dias_subsidio} días subsidio CAJA (40% patrono)'
                    )
                    db.session.add(concepto_incapacidad_subsidio)
                
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
        paginated_nominas = query.paginate(page=page, per_page=9, error_out=False)

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
    
""" Función para ver el detalle de una nómina con deducciones desglosadas --------"""
@registro_asistencia_bp.route('/nomina/detalle/<int:id_nomina>', methods=['GET'])
@permiso_requerido('listar_nominas')
@login_required
def ver_detalle_nomina(id_nomina):
    """Muestra la boleta de pago detallada con todas las deducciones y conceptos."""
    try:
        nomina = Nomina.query.get_or_404(id_nomina)
        deducciones = Deduccion.query.filter_by(Nomina_id_nomina=id_nomina).all()
        conceptos = ConceptoNomina.query.filter_by(Nomina_id_nomina=id_nomina).all()
        
        return render_template(
            'nomina/detalle_nomina.html',
            nomina=nomina,
            deducciones=deducciones,
            conceptos=conceptos,
            empleado=nomina.empleado
        )
    except Exception as e:
        flash(f'Ocurrió un error al cargar el detalle de la nómina: {str(e)}', 'danger')
        return redirect(url_for('registro_asistencia.listar_nominas'))

""" Función para imprimir la boleta de pago en PDF --------------------------------"""
@registro_asistencia_bp.route('/nomina/imprimir/<int:id_nomina>', methods=['GET'])
@permiso_requerido('listar_nominas')
@login_required
def imprimir_boleta_pago(id_nomina):
    """Genera un PDF de la boleta de pago con deducciones desglosadas."""
    try:
        import io
        from datetime import datetime
        
        nomina = Nomina.query.get_or_404(id_nomina)
        deducciones = Deduccion.query.filter_by(Nomina_id_nomina=id_nomina).all()
        conceptos = ConceptoNomina.query.filter_by(Nomina_id_nomina=id_nomina).all()
        
        # 1. Iniciamos la lista con los datos generales básicos
        rows = [
            ('Empleado', nomina.empleado.nombre_completo if nomina.empleado else 'N/A'),
            ('Cédula', nomina.empleado.cedula if nomina.empleado else 'N/A'),
            ('Puesto', nomina.empleado.puesto.tipo_puesto if nomina.empleado and nomina.empleado.puesto else 'N/A'),
            ('Tipo de Nómina', nomina.tipo_nomina_relacion.nombre_tipo if nomina.tipo_nomina_relacion else 'N/A'),
            ('Salario Bruto', f"₡ {nomina.salario_bruto:,.2f}"),
        ]
        
        # 2. Iteramos dinámicamente las deducciones reales encontradas en la BD
        for ded in deducciones:
            # Si tiene porcentaje (ej. 5.5), se lo pegamos al nombre de forma limpia
            porcentaje_str = f" ({ded.porcentaje}%)" if ded.porcentaje else ""
            nombre_deduccion = f"Deducción: {ded.tipo_deduccion}{porcentaje_str}"
            monto_deduccion = f"₡ {ded.monto:,.2f}"
            
            rows.append((nombre_deduccion, monto_deduccion))
            
        # 3. Agregamos los totales finales de cierre
        rows.append(('Total Deducciones', f"₡ {nomina.deducciones:,.2f}"))
        rows.append(('Salario Neto', f"₡ {nomina.salario_neto:,.2f}"))
        
        metadata = {
            'Período': f"{nomina.fecha_inicio.strftime('%d/%m/%Y')} a {nomina.fecha_fin.strftime('%d/%m/%Y')}",
            'Fecha de generación': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        }
        
        # 4. Usamos la función optimizada de pdf_utils que creamos previamente
        pdf_file = build_pdf_from_rows(
            title='BOLETA DE PAGO',
            rows=rows,
            metadata=metadata,
        )
        
        response = make_response(pdf_file)
        response.headers['Content-Type'] = 'application/pdf'
        
        # Opcional: Si cambiás 'attachment' por 'inline', se abrirá directo en el navegador en vez de forzar la descarga
        response.headers['Content-Disposition'] = f'inline; filename=boleta_pago_{nomina.id_nomina}.pdf'
        
        return response
    except Exception as e:
        flash(f'Ocurrió un error al generar el PDF: {str(e)}', 'danger')
        return redirect(url_for('registro_asistencia.listar_nominas'))
    
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
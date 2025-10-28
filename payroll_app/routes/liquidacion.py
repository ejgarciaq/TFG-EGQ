from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from sqlalchemy import func
import logging
from payroll_app import db
from payroll_app.models import Empleado, Nomina, Liquidacion, Usuario 
from payroll_app.routes.decorators import permiso_requerido 

# Define tu Blueprint para el módulo de liquidación
liquidacion_bp = Blueprint('liquidacion', __name__)

""" Constantes para cálculos de liquidación """
MESES_PROMEDIO_BASE = 6 
DIAS_MES = 30 # Usado para proporcionalidad y salario diario
DIAS_AGUINALDO_POR_ANIO = 360 # Usado para proporcionalidad del aguinaldo (dividir entre 12) 

# --- FUNCIONES AUXILIARES DE CÁLCULO ---

""" Cálculo de Liquidación Proporcional según la Ley de Costa Rica """
def _calcular_dias_preaviso(meses_servicio):
    """Calcula los días de preaviso según la antigüedad (Art. 28, Código de Trabajo)."""
    if meses_servicio < 3:
        return 0
    elif meses_servicio < 6:
        return 7
    elif meses_servicio < 12:
        return 15
    else: # 12 meses o más
        return 30

""" Cálculo de Cesantía según la Ley de Costa Rica """
def _calcular_dias_cesantia(meses_servicio):
    """
    Calcula los días de cesantía según la tabla progresiva (Art. 29, Código de Trabajo).
    Esta función es el cambio clave para apegarse a la ley CR.
    """
    # Si tiene menos de 6 meses, no tiene derecho a cesantía.
    if meses_servicio < 6:
        return 0.0
    # Tabla de Cesantía (Días de salario por año completo)
    # Fuente: Art. 29, Código de Trabajo.
    dias_por_anio = [
        0,     # Meses 0-6 (se manejará por la condición inicial)
        19.5,  # 6 meses a 1 año (proporcional)
        20.0,  # 1 a 2 años
        20.62, # 2 a 3 años
        20.83, # 3 a 4 años
        21.25, # 4 a 5 años
        21.25, # 5 a 6 años
        21.25, # 6 a 7 años
        21.25, # 7 a 8 años
    ]
    # Límite máximo de 8 años (96 meses)
    if meses_servicio > 96:
        meses_servicio = 96 
    # Desglose de meses en años completos y meses residuales
    anios_completos = int(meses_servicio // 12)
    meses_residuales = meses_servicio % 12
    dias_cesantia_total = 0.0
    # 1. Calcular años completos (hasta el límite de la tabla)
    for i in range(1, anios_completos + 1):
        # El índice se ajusta al límite de la tabla
        index = min(i, len(dias_por_anio) - 1)
        dias_cesantia_total += dias_por_anio[index]
    # 2. Calcular la fracción residual (meses)
    if meses_residuales > 0:
        # La fracción se calcula con la tarifa del año en curso (anios_completos + 1)
        # Si el empleado tiene 1 año y 3 meses, la tarifa para la fracción es la del 2do año (20.0 días)
        anio_actual = anios_completos + 1
        index = min(anio_actual, len(dias_por_anio) - 1)
        # Proporcionalidad: (meses_residuales / 12 meses) * días_correspondientes_al_año
        if anio_actual == 1 and meses_residuales < 6:
             # Caso especial: 6 a 12 meses.
            dias_residuales = (meses_residuales * DIAS_MES / DIAS_AGUINALDO_POR_ANIO) * 19.5
        elif meses_residuales > 0:
            dias_residuales = (meses_residuales / 12) * dias_por_anio[index]
        dias_cesantia_total += dias_residuales
    return round(dias_cesantia_total, 2)

""" Cálculo del Salario Promedio de los últimos 6 meses """
def _obtener_salario_base_promedio(empleado, fecha_fin_contrato):
    """Calcula el salario promedio (bruto) de los últimos 6 meses."""
    fecha_inicio_periodo = fecha_fin_contrato - relativedelta(months=MESES_PROMEDIO_BASE)
    
    total_bruto = db.session.query(func.sum(Nomina.salario_bruto)).filter(
        Nomina.Empleado_id_empleado == empleado.id_empleado,
        Nomina.fecha_fin <= fecha_fin_contrato,
        Nomina.fecha_inicio >= fecha_inicio_periodo
    ).scalar() or 0.0
    
    if total_bruto == 0.0:
        return 0.0
    
    antiguedad_meses = (fecha_fin_contrato.year - empleado.fecha_ingreso.year) * 12 + \
                       (fecha_fin_contrato.month - empleado.fecha_ingreso.month)
    
    meses_a_dividir = min(MESES_PROMEDIO_BASE, antiguedad_meses)
    divisor = meses_a_dividir if meses_a_dividir > 0 else 1
    
    salario_promedio_mensual = round(total_bruto / divisor, 2)
    return salario_promedio_mensual

""" Cálculo del Salario Pendiente de Pago """
def _calcular_salario_pendiente(empleado, fecha_fin_contrato, salario_promedio_diario):
    """Calcula el salario bruto pendiente de pago."""
    ultima_nomina = Nomina.query.filter(Nomina.Empleado_id_empleado == empleado.id_empleado, Nomina.fecha_fin <= fecha_fin_contrato).order_by(Nomina.fecha_fin.desc()).first()

    fecha_inicio_pago = empleado.fecha_ingreso if not ultima_nomina else ultima_nomina.fecha_fin + timedelta(days=1)
    dias_pendientes = (fecha_fin_contrato - fecha_inicio_pago).days + 1
    
    return round(dias_pendientes * salario_promedio_diario, 2) if dias_pendientes > 0 else 0.0

""" Cálculo Completo de la Liquidación Proporcional """
def _calcular_liquidacion_proporcional(empleado, fecha_fin_contrato, salario_promedio_mensual, causa_despido):
    """ Cálculo completo de la liquidación proporcional, apegado a la ley CR. """
    fecha_inicio_contrato = empleado.fecha_ingreso 
    antiguedad = relativedelta(fecha_fin_contrato, fecha_inicio_contrato)
    meses_servicio = (antiguedad.years * 12) + antiguedad.months + (antiguedad.days / DIAS_MES)
    salario_promedio_diario = salario_promedio_mensual / DIAS_MES if salario_promedio_mensual > 0 else 0.0
    # LÓGICA CONDICIONAL DE PREAVISO Y CESANTÍA
    if causa_despido in ['sin_justa_causa', 'despido_indirecto']:
        dias_preaviso = _calcular_dias_preaviso(meses_servicio)
        monto_preaviso = round(dias_preaviso * salario_promedio_diario, 2)
        
        # 🛑 USO DE LA FUNCIÓN CORREGIDA DE CESANTÍA
        dias_cesantia = _calcular_dias_cesantia(meses_servicio) 
        monto_cesantia = round(dias_cesantia * salario_promedio_diario, 2)
    else:
        dias_preaviso = 0
        monto_preaviso = 0.0
        dias_cesantia = 0
        monto_cesantia = 0.0
    # CÁLCULO DE VACACIONES PENDIENTES
    dias_vacaciones_pendientes = empleado.vacaciones_disponibles or 0
    monto_vacaciones = round(dias_vacaciones_pendientes * salario_promedio_diario, 2)
    # CÁLCULO DE AGUINALDO PROPORCIONAL
    anio_corte = fecha_fin_contrato.year if fecha_fin_contrato.month >= 12 and fecha_fin_contrato.day >= 1 else fecha_fin_contrato.year - 1 
    fecha_inicio_aguinaldo = datetime(anio_corte, 12, 1).date() 
    dias_acumulados_aguinaldo = (fecha_fin_contrato - fecha_inicio_aguinaldo).days + 1
    total_bruto_aguinaldo = db.session.query(func.sum(Nomina.salario_bruto)).filter(
        Nomina.Empleado_id_empleado == empleado.id_empleado,
        Nomina.fecha_fin <= fecha_fin_contrato,
        Nomina.fecha_inicio >= fecha_inicio_aguinaldo
    ).scalar() or 0.0
    monto_aguinaldo = round(total_bruto_aguinaldo / 12, 2) 
    # CÁLCULO DE SALARIO PENDIENTE
    monto_salario_pendiente = _calcular_salario_pendiente(empleado, fecha_fin_contrato, salario_promedio_diario)
    # RESUMEN:
    total_liquidacion = monto_preaviso + monto_cesantia + monto_vacaciones + monto_aguinaldo + monto_salario_pendiente

    return {
        'total_liquidacion': total_liquidacion,
        'monto_preaviso': monto_preaviso,
        'dias_preaviso': dias_preaviso,
        'monto_cesantia': monto_cesantia,
        'dias_cesantia': dias_cesantia,
        'monto_vacaciones': monto_vacaciones,
        'dias_vacaciones': dias_vacaciones_pendientes,
        'monto_aguinaldo': monto_aguinaldo,
        'monto_salario_pendiente': monto_salario_pendiente, 
        'salario_promedio_mensual': salario_promedio_mensual,
        'salario_promedio_diario': salario_promedio_diario,
        'meses_servicio': round(meses_servicio, 2),
        'fecha_inicio_contrato': fecha_inicio_contrato,
        'fecha_fin_contrato': fecha_fin_contrato,
        'fecha_inicio_aguinaldo': fecha_inicio_aguinaldo,
        'dias_acumulados_aguinaldo': dias_acumulados_aguinaldo,
        'causa_despido': causa_despido 
    }

""" RUTAS DEL MÓDULO DE LIQUIDACIÓN """

""" Página para buscar el empleado y los datos iniciales. """
@liquidacion_bp.route('/calcular', methods=['GET', 'POST'])
@permiso_requerido('ca_liquidacion')
@login_required
def buscar_empleado():
    """ Muestra el formulario para seleccionar el empleado, la fecha de fin y la causa. """
    empleados = Empleado.query.filter_by(estado_empleado=True).all()
    today = datetime.now().date()
    fecha_fin_contrato = today

    causas = [
        ('sin_justa_causa', 'Despido sin justa causa'),
        ('con_justa_causa', 'Despido con justa causa'),
        ('renuncia', 'Renuncia Voluntaria'),
        ('despido_indirecto', 'Despido Indirecto (Renuncia por falta patronal)')
    ]
    
    if request.method == 'POST':
        empleado_id = request.form.get('empleado_id')
        fecha_fin_str = request.form.get('fecha_fin_contrato')
        causa_despido = request.form.get('causa_despido') 

        try:
            empleado = Empleado.query.get(empleado_id)
            fecha_fin_contrato = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            
            if not empleado:
                flash('Empleado no encontrado.', 'danger')
                return redirect(url_for('liquidacion.buscar_empleado'))
            
        except (ValueError, TypeError):
            flash('Error en los datos de entrada (Empleado o Fecha).', 'danger')
            return redirect(url_for('liquidacion.buscar_empleado'))
            
        return redirect(url_for('liquidacion.mostrar_calculo', empleado_id=empleado_id, fecha_fin=fecha_fin_str, causa=causa_despido))

    return render_template('liquidacion/liquidacion.html', empleados=empleados, today=today, fecha_fin_contrato=fecha_fin_contrato, causas=causas)

""" Página para mostrar el cálculo detallado y guardar la liquidación. """
@liquidacion_bp.route('/calculo/<int:empleado_id>/<string:fecha_fin>', methods=['GET', 'POST'])
@permiso_requerido('ca_liquidacion')
@login_required
def mostrar_calculo(empleado_id, fecha_fin):
    """ Muestra el cálculo detallado y maneja el guardado. """
    
    empleado = Empleado.query.get_or_404(empleado_id)
    fecha_fin_contrato = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    causa_despido = request.args.get('causa', 'renuncia') 

    try:
        usuario = Usuario.query.get(empleado.Usuario_id_usuario)
    except ArithmeticError:
        usuario = None
        logging.warning(f"No se pudo encontrar el objeto Usuario para el empleado {empleado_id}")
    
    try:
        salario_promedio = _obtener_salario_base_promedio(empleado, fecha_fin_contrato)
        
        if salario_promedio == 0.0 and empleado.fecha_ingreso < (fecha_fin_contrato - relativedelta(months=MESES_PROMEDIO_BASE)):
            flash(f'Advertencia (FA1): Faltan registros de nómina en los últimos {MESES_PROMEDIO_BASE} meses para calcular el salario promedio. La cesantía/preaviso se calculará con salario base $0.00.','warning')
            
        resultados = _calcular_liquidacion_proporcional(empleado, fecha_fin_contrato, salario_promedio, causa_despido)
        
        if request.method == 'POST':
            if resultados['total_liquidacion'] > 0:
                nueva_liquidacion = Liquidacion(
                    fecha_pago=datetime.now().date(), 
                    fecha_fin_contrato=fecha_fin_contrato,
                    total_monto=resultados['total_liquidacion'],
                    monto_preaviso=resultados['monto_preaviso'],
                    monto_cesantia=resultados['monto_cesantia'],
                    monto_vacaciones=resultados['monto_vacaciones'],
                    monto_aguinaldo=resultados['monto_aguinaldo'],
                    monto_salario_pendiente=resultados['monto_salario_pendiente'], 
                    Empleado_id_empleado=empleado.id_empleado
                )
                db.session.add(nueva_liquidacion)

                if usuario:
                    usuario.estado_usuario = False
                
                empleado.estado_usuario = False
                empleado.estado_empleado = False
                empleado.fecha_salida = fecha_fin_contrato
                
                db.session.commit()
                flash('¡Éxito! Liquidación calculada y guardada en el historial. El estado del empleado ha sido actualizado.', 'success')
                return redirect(url_for('liquidacion.buscar_empleado', empleado_id=empleado.id_empleado))
            else:
                flash('Liquidación no guardada. El monto total es $0.00.', 'info')
                
    except Exception as e:
        db.session.rollback()
        logging.exception("Error al generar el cálculo de liquidación.")
        flash('Error al calcular la liquidación. Por favor, intente de nuevo. (FA2)', 'danger')
        return redirect(url_for('liquidacion.buscar_empleado'))
        
    return render_template('liquidacion/detalle_liquidacion.html', 
                           empleado=empleado, 
                           resultados=resultados,
                           fecha_fin_contrato=fecha_fin_contrato)
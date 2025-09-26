from datetime import datetime, timedelta # Importa timedelta
from dateutil.relativedelta import relativedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from sqlalchemy import func
import logging
from payroll_app import db
from payroll_app.models import Empleado, Nomina, Liquidacion 
from payroll_app.routes.decorators import permiso_requerido 

# Define tu Blueprint para el módulo de liquidación
""" blueprint de Liquidación """
liquidacion_bp = Blueprint('liquidacion', __name__)

""" Constantes para cálculos de liquidación """
MESES_PROMEDIO_BASE = 6 
DIAS_MES = 30 
DIAS_AGUINALDO_POR_ANIO = 360 

def _calcular_dias_preaviso(meses_servicio):
    """Calcula los días de preaviso según la antigüedad (simplificado)."""
    if meses_servicio < 3:
        return 0
    elif meses_servicio < 6:
        return 7
    elif meses_servicio < 12:
        return 15
    else: # 1 año o más
        return 30

""" Cálculo de días de cesantía (simplificado) """
def _calcular_dias_cesantia(meses_servicio):
    if meses_servicio < 6:
        return 0
    
    # Días de cesantía acumulados (30 días por cada 360 días trabajados)
    dias_servicio = meses_servicio * DIAS_MES
    dias_cesantia = (dias_servicio / DIAS_AGUINALDO_POR_ANIO) * DIAS_MES
    return dias_cesantia

""" FUNCIONES AUXILIARES DE CÁLCULO DE LIQUIDACIÓN """
"""
    Calcula el salario promedio (bruto) de los últimos MESES_PROMEDIO_BASE meses
    para usar como base en Preaviso y Cesantía.
"""
def _obtener_salario_base_promedio(empleado, fecha_fin_contrato):

    fecha_inicio_periodo = fecha_fin_contrato - relativedelta(months=MESES_PROMEDIO_BASE)
    
    total_bruto = db.session.query(func.sum(Nomina.salario_bruto)).filter(
        Nomina.Empleado_id_empleado == empleado.id_empleado,
        Nomina.fecha_fin <= fecha_fin_contrato,
        Nomina.fecha_inicio >= fecha_inicio_periodo
    ).scalar() or 0.0

    conteo_nominas = db.session.query(Nomina).filter(
        Nomina.Empleado_id_empleado == empleado.id_empleado,
        Nomina.fecha_fin <= fecha_fin_contrato,
        Nomina.fecha_inicio >= fecha_inicio_periodo
    ).count()

    if total_bruto == 0.0 or conteo_nominas == 0:
        return 0.0
    
    # CORRECCIÓN DE LA LÓGICA DEL DIVISOR:
    # Si hay nóminas, el divisor debe ser el número de nóminas encontradas
    # o el número fijo (6), el que sea más apropiado según tu ley.
    # Aquí usamos el conteo real de nóminas (asumiendo pagos mensuales) o el máximo (6)
    
    # Si pagas mensual: conteo_nominas representa el número de meses pagados
    divisor = conteo_nominas
    
    if divisor == 0:
        return 0.0 # Evita división por cero
    
    # Promedio mensual: Dividimos la suma total entre el número de meses/nóminas encontrados
    salario_promedio_mensual = round(total_bruto / divisor, 2)
    
    return salario_promedio_mensual

"""
    Calcula el salario bruto pendiente de pago desde el último día de nómina
    hasta la fecha de fin de contrato.
"""
def _calcular_salario_pendiente(empleado, fecha_fin_contrato, salario_promedio_diario):
    # 1 Encontrar la fecha de fin de la ÚLTIMA nómina pagada.
    # Filtramos las nóminas cuya fecha_fin sea menor o igual a la fecha de fin de contrato
    ultima_nomina = Nomina.query.filter(
                                 Nomina.Empleado_id_empleado == empleado.id_empleado,
                                 Nomina.fecha_fin <= fecha_fin_contrato
                                 ) \
                                 .order_by(Nomina.fecha_fin.desc()) \
                                 .first()

    # Definir la fecha de inicio del periodo pendiente
    if not ultima_nomina:
        # Si no hay nóminas, el salario pendiente es desde la fecha de ingreso
        fecha_inicio_pago = empleado.fecha_ingreso
    else:
        # El periodo de pago pendiente inicia el día siguiente al fin de la última nómina
        fecha_inicio_pago = ultima_nomina.fecha_fin + timedelta(days=1)
        
    # Calcular los días pendientes
    dias_pendientes = (fecha_fin_contrato - fecha_inicio_pago).days + 1 # Incluye el día de fin de contrato
    
    if dias_pendientes <= 0:
        return 0.0
    
    # 4. Calcular el monto
    monto_pendiente = dias_pendientes * salario_promedio_diario
    
    return round(monto_pendiente, 2)

"""   Cálculo completo de la liquidación proporcional."""
def _calcular_liquidacion_proporcional(empleado, fecha_fin_contrato, salario_promedio_mensual):

    fecha_inicio_contrato = empleado.fecha_ingreso 

    # ANTIGÜEDAD Y SALARIO DIARIO
    antiguedad = relativedelta(fecha_fin_contrato, fecha_inicio_contrato)
    meses_servicio = (antiguedad.years * 12) + antiguedad.months + (antiguedad.days / DIAS_MES)
    
    if salario_promedio_mensual > 0:
        salario_promedio_diario = salario_promedio_mensual / DIAS_MES 
    else:
        salario_promedio_diario = 0.0
    
    # CÁLCULO DE PREAVISO
    dias_preaviso = _calcular_dias_preaviso(meses_servicio)
    monto_preaviso = round(dias_preaviso * salario_promedio_diario, 2)
    
    # CÁLCULO DE CESANTÍA
    dias_cesantia = _calcular_dias_cesantia(meses_servicio)
    monto_cesantia = round(dias_cesantia * salario_promedio_diario, 2)

    # CÁLCULO DE VACACIONES PENDIENTES
    dias_vacaciones_pendientes = empleado.vacaciones_disponibles or 0
    monto_vacaciones = round(dias_vacaciones_pendientes * salario_promedio_diario, 2)
    
    # CÁLCULO DE AGUINALDO PROPORCIONAL
    
    if fecha_fin_contrato.month < 12 or (fecha_fin_contrato.month == 12 and fecha_fin_contrato.day < 1):
        anio_corte = fecha_fin_contrato.year - 1 
    else:
        anio_corte = fecha_fin_contrato.year
    
    fecha_inicio_aguinaldo = datetime(anio_corte, 12, 1).date() 
    
    dias_acumulados_aguinaldo = (fecha_fin_contrato - fecha_inicio_aguinaldo).days
    
    total_bruto_aguinaldo = db.session.query(func.sum(Nomina.salario_bruto)).filter(
        Nomina.Empleado_id_empleado == empleado.id_empleado,
        Nomina.fecha_fin <= fecha_fin_contrato,
        Nomina.fecha_inicio >= fecha_inicio_aguinaldo
    ).scalar() or 0.0
    
    monto_aguinaldo = round(total_bruto_aguinaldo / 12, 2) 
    
    # 6. CÁLCULO DE SALARIO PENDIENTE (NUEVO RUBRO)
    monto_salario_pendiente = _calcular_salario_pendiente(
        empleado, 
        fecha_fin_contrato, 
        salario_promedio_diario
    )
    
    # 7. RESUMEN: INCLUYE EL SALARIO PENDIENTE
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
    }

""" Ruta para iniciar el proceso de cálculo de liquidación """

"""
    Muestra el formulario para seleccionar el empleado y la fecha de fin.
"""
@liquidacion_bp.route('/calcular', methods=['GET', 'POST'])
@permiso_requerido('ca_liquidacion')
@login_required
def buscar_empleado():

    empleados = Empleado.query.filter_by(estado_empleado=True).all()
    today = datetime.now().date()
    fecha_fin_contrato = today

    if request.method == 'POST':
        empleado_id = request.form.get('empleado_id')
        fecha_fin_str = request.form.get('fecha_fin_contrato')
        
        try:
            empleado = Empleado.query.get(empleado_id)
            fecha_fin_contrato = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            
            if not empleado:
                flash('Empleado no encontrado.', 'danger')
                return redirect(url_for('liquidacion.buscar_empleado'))
            
        except (ValueError, TypeError):
            flash('Error en los datos de entrada (Empleado o Fecha).', 'danger')
            return redirect(url_for('liquidacion.buscar_empleado'))
            
        return redirect(url_for('liquidacion.mostrar_calculo', empleado_id=empleado_id, fecha_fin=fecha_fin_str))

    return render_template('liquidacion/liquidacion.html', empleados=empleados, today=today, fecha_fin_contrato=fecha_fin_contrato)

""" Ruta para mostrar el cálculo detallado y manejar el guardado """
@liquidacion_bp.route('/calculo/<int:empleado_id>/<string:fecha_fin>', methods=['GET', 'POST'])
@permiso_requerido('ca_liquidacion')
@login_required
def mostrar_calculo(empleado_id, fecha_fin):
    
    empleado = Empleado.query.get_or_404(empleado_id)
    fecha_fin_contrato = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    
    # Ejecución del Cálculo
    try:
        # Recuperar y calcular el salario promedio
        salario_promedio = _obtener_salario_base_promedio(empleado, fecha_fin_contrato)
        
        #  Datos de cálculo incompletos
        if salario_promedio == 0.0 and empleado.fecha_ingreso < (fecha_fin_contrato - relativedelta(months=MESES_PROMEDIO_BASE)):
            # Aquí la advertencia es válida: si no hay datos de nómina en los últimos 6 meses.
            flash(f'Advertencia (FA1): Faltan registros de nómina en los últimos {MESES_PROMEDIO_BASE} meses para calcular el salario promedio. La cesantía/preaviso se calculará con salario base $0.00.','warning')
            
        # 2. Ejecutar el cálculo completo
        resultados = _calcular_liquidacion_proporcional(empleado, fecha_fin_contrato, salario_promedio)
        
        # ----------------------------------------------------
        # Guardado de la Liquidación (POST)
        # ----------------------------------------------------
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
                # Actualizar el estado del empleado
                empleado.estado_empleado = False
                empleado.fecha_salida = fecha_fin_contrato
                
                db.session.commit()
                flash('¡Éxito! Liquidación calculada y guardada en el historial. El estado del empleado ha sido actualizado.', 'success')
                # Asumo que la ruta 'empleado.ver_perfil' existe y usa 'empleado_id'
                return redirect(url_for('empleado.ver_perfil_empleado', empleado_id=empleado.id_empleado))
            else:
                flash('Liquidación no guardada. El monto total es $0.00.', 'info')
                
    except Exception as e:
        # FA2 - Error en el cálculo
        db.session.rollback()
        logging.exception("Error al generar el cálculo de liquidación.")
        flash('Error al calcular la liquidación. Por favor, intente de nuevo. (FA2)', 'danger')
        return redirect(url_for('liquidacion.buscar_empleado'))
        
    # Presentar el desglose
    return render_template('liquidacion/detalle_liquidacion.html', 
                           empleado=empleado, 
                           resultados=resultados,
                           fecha_fin_contrato=fecha_fin_contrato)
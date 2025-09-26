from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from sqlalchemy import func
import logging, calendar
from datetime import datetime
from payroll_app import db
from payroll_app.models import Empleado, TipoNomina, Nomina, Aguinaldo
from payroll_app.routes.decorators import permiso_requerido 

""" Módulo de Cálculo de Aguinaldo"""
aguinaldo_bp = Blueprint('aguinaldo', __name__)

"""CONSTANTES DE CÁLCULO (Ajusta según tu legislación, ej. Costa Rica) ---
 Periodo de cálculo: 1 de Diciembre del año anterior al 30 de Noviembre del año en curso """
MES_INICIO_CALCULO = 12 
DIA_INICIO_CALCULO = 1
MES_FIN_CALCULO = 11
DIA_FIN_CALCULO = 30
MESES_PROMEDIO = 12

""" FUNCIONES AUXILIARES DE CÁLCULO """
""" Calcula el aguinaldo para un empleado en un año fiscal dado. """
@login_required
def _calcular_aguinaldo_empleado(empleado, anio_fiscal):
    # Definir el período de cálculo: Dic. del año anterior a Nov. del año actual
    anio_anterior = anio_fiscal - 1
    
    fecha_inicio_periodo = datetime(anio_anterior, MES_INICIO_CALCULO, DIA_INICIO_CALCULO).date()
    fecha_fin_periodo = datetime(anio_fiscal, MES_FIN_CALCULO, DIA_FIN_CALCULO).date()
    
    # Obtener la suma de salarios brutos de las nóminas en el período
    # Utilizamos la tabla 'Nomina' para obtener el 'salario_bruto' ya calculado
    total_bruto = db.session.query(func.sum(Nomina.salario_bruto)).filter(
        Nomina.empleado == empleado,
        Nomina.fecha_inicio >= fecha_inicio_periodo,
        Nomina.fecha_fin <= fecha_fin_periodo
    ).scalar() or 0.0

    # Obtener el número de meses con registros (para el cálculo proporcional)
    # Contamos la cantidad de nóminas en el período, usando GROUP BY si la periodicidad es menor a mensual
    # Para la práctica, contaremos cuántas nóminas existen
    meses_con_nomina = db.session.query(Nomina.fecha_inicio).filter(
        Nomina.empleado == empleado,
        Nomina.fecha_inicio >= fecha_inicio_periodo,
        Nomina.fecha_fin <= fecha_fin_periodo
    ).distinct().count()

    # Calcular el monto final
    if meses_con_nomina == 0 or total_bruto == 0:
        return 0.0, 0, fecha_inicio_periodo, fecha_fin_periodo # Monto, Meses, Inicio, Fin
    
    # Cálculo proporcional: (Suma Bruta / 12)
    monto_aguinaldo = round(total_bruto / MESES_PROMEDIO, 2)

    return monto_aguinaldo, meses_con_nomina, fecha_inicio_periodo, fecha_fin_periodo

# -----------------------------------------------------------------
""" calcular_aguinaldo: Vista principal para calcular y listar aguinaldos """
@aguinaldo_bp.route('/calcular', methods=['GET', 'POST'])
@permiso_requerido('cal_aguinaldo') # RNF-SE-018
def calcular_aguinaldo():
    
    tipos_nomina = TipoNomina.query.all()
    
    if request.method == 'POST':
        # --- Obtención de Parámetros del Formulario ---
        anio_str = request.form.get('anio_fiscal')
        tipo_nomina_id_str = request.form.get('tipo_nomina_id')
        
        # Validaciones de Parámetros
        try:
            anio_fiscal = int(anio_str)
            tipo_nomina_id = int(tipo_nomina_id_str) if tipo_nomina_id_str else None
        except (ValueError, TypeError):
            flash('Error en los parámetros de entrada. Verifique el año fiscal y el tipo de nómina.', 'danger')
            return redirect(url_for('aguinaldo.calcular_aguinaldo'))
            
        if anio_fiscal <= 2000 or anio_fiscal > datetime.now().year + 1:
            flash('Año fiscal inválido.', 'danger')
            return redirect(url_for('aguinaldo.calcular_aguinaldo'))
            
        # --- 1. Filtrar Empleados ---
        query_empleados = Empleado.query
        if tipo_nomina_id:
            query_empleados = query_empleados.filter_by(TipoNomina_id_tipo_nomina=tipo_nomina_id)
            
        empleados_a_procesar = query_empleados.all()
        
        if not empleados_a_procesar:
            flash('No se encontraron empleados para el filtro seleccionado.', 'warning')
            return redirect(url_for('aguinaldo.calcular_aguinaldo'))
            
        nominas_procesadas = []
        aguinaldos_generados = 0
        
        # --- 2. Bucle de Cálculo ---
        try:
            for empleado in empleados_a_procesar:
                
                # Precondición: Verificar si ya existe un cálculo de aguinaldo para ese año
                aguinaldo_existente = Aguinaldo.query.filter(
                    Aguinaldo.Empleado_id_empleado == empleado.id_empleado,
                    db.extract('year', Aguinaldo.fecha_pago) == anio_fiscal
                ).first()
                
                if aguinaldo_existente:
                    nominas_procesadas.append({'nombre': empleado.nombre_completo, 'monto': None, 'estado': 'Ya Existe', 'motivo': 'Aguinaldo ya calculado y guardado para este año.'})
                    continue
                
                # Ejecutar el cálculo (Paso 6)
                monto_aguinaldo, meses_con_nomina, fecha_inicio, fecha_fin = _calcular_aguinaldo_empleado(empleado, anio_fiscal)

                if monto_aguinaldo == 0.0 and meses_con_nomina > 0:
                    # FA1: Salarios incompletos (o salario_bruto en 0 en Nomina)
                    nominas_procesadas.append({'nombre': empleado.nombre_completo, 'monto': 0.0, 'estado': 'Advertencia', 'motivo': f'Cálculo resultó en $0.00. (Meses con Nomina: {meses_con_nomina}). Revisar registros.'})
                    continue
                
                if monto_aguinaldo == 0.0 and meses_con_nomina == 0:
                    # FA1: Falta de Registros
                    nominas_procesadas.append({'nombre': empleado.nombre_completo, 'monto': 0.0, 'estado': 'Advertencia', 'motivo': 'No se encontraron registros de nómina válidos en el período de cálculo.'})
                    continue
                
                # 3. Guardar el resultado (Paso 7, 8)
                # NOTA: Usamos la fecha de pago como Diciembre 15 del año fiscal (ejemplo)
                fecha_pago_aguinaldo = datetime(anio_fiscal, 12, 15).date() 
                
                nuevo_aguinaldo = Aguinaldo(
                    fecha_pago=fecha_pago_aguinaldo,
                    monto=monto_aguinaldo,
                    Empleado_id_empleado=empleado.id_empleado
                )
                db.session.add(nuevo_aguinaldo)
                aguinaldos_generados += 1
                
                nominas_procesadas.append({
                    'nombre': empleado.nombre_completo, 
                    'monto': f'${monto_aguinaldo:,.2f}', 
                    'estado': 'Éxito',
                    'motivo': f'Calculado con {meses_con_nomina} meses de salario. Periodo: {fecha_inicio} a {fecha_fin}.'
                })
                
            # --- 4. Commit y Flashes ---
            db.session.commit()
            
            if aguinaldos_generados > 0:
                flash(f'¡Éxito! Se calcularon y guardaron {aguinaldos_generados} registros de aguinaldo.', 'success')
            else:
                flash('Proceso finalizado. No se generaron nuevos aguinaldos (revisar advertencias).', 'warning')
                
            # Opcional: Flashear los detalles de las advertencias
            for resultado in nominas_procesadas:
                if resultado['estado'] == 'Advertencia' or resultado['estado'] == 'Ya Existe':
                    flash(f"[{resultado['estado']}] {resultado['nombre']}: {resultado['motivo']}", 'info')
            
            # Mantenemos los parámetros del POST en la redirección si es exitoso
            return redirect(url_for('aguinaldo.calcular_aguinaldo', anio_fiscal=anio_str, tipo_nomina_id=tipo_nomina_id_str))
            
        except Exception as e:
            # FA2: Error en el cálculo
            db.session.rollback()
            logging.exception("Error al generar el aguinaldo.")
            flash('No se pudo calcular el aguinaldo. Por favor, intente de nuevo.', 'danger')
            return redirect(url_for('aguinaldo.calcular_aguinaldo'))
            
    # --- GET: Cargar la vista inicial (RNF-US-018) ---
    
    # 1. Obtener el año actual para pre-seleccionar en el formulario
    anio_actual = datetime.now().year
    
    # 💡 IMPLEMENTACIÓN DE PAGINACIÓN:
    # 1. Obtener el número de página de la URL (por defecto, es la página 1)
    page = request.args.get('page', 1, type=int)
    per_page = 5  # Define el número de registros por página (ej. 10)
    
    # 2. Realizar la consulta con .paginate()
    # Usamos db.session.query(Aguinaldo, Empleado).join(Empleado) para obtener la tupla necesaria.
    aguinaldos_paginados = db.session.query(Aguinaldo, Empleado) \
        .join(Empleado) \
        .order_by(Aguinaldo.fecha_pago.desc(), Aguinaldo.id_aguinaldo.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False) # error_out=False para evitar 404 si la página no existe
    
    # 3. Pasar el objeto de paginación a la plantilla
    return render_template('aguinaldo/calcular_aguinaldo.html', 
                            tipos_nomina=tipos_nomina, 
                            aguinaldos_paginados=aguinaldos_paginados, # 💡 Se cambió el nombre de la variable
                            anio_actual=anio_actual)

""" ver_detalle: Muestra los detalles del cálculo del aguinaldo específico para auditoría """
@aguinaldo_bp.route('/detalle/<int:aguinaldo_id>', methods=['GET'])
@permiso_requerido('cal_aguinaldo') # RNF-SE-018
@login_required
def ver_detalle(aguinaldo_id):
    """
    RNF-US-018: Muestra los detalles del cálculo del aguinaldo específico
    para auditoría.
    """
    
    # 1. Buscar el registro de aguinaldo
    aguinaldo = Aguinaldo.query.get_or_404(aguinaldo_id)
    
    # 2. Obtener el empleado asociado
    empleado = aguinaldo.empleado_relacion
    
    # 3. Determinar el período de cálculo basado en la fecha de pago (similar a _calcular_aguinaldo_empleado)
    anio_fiscal = aguinaldo.fecha_pago.year
    anio_anterior = anio_fiscal - 1
    
    # Período de cálculo: 1 de Dic. del año anterior al 30 de Nov. del año actual
    fecha_inicio_periodo = datetime(anio_anterior, MES_INICIO_CALCULO, DIA_INICIO_CALCULO).date()
    fecha_fin_periodo = datetime(anio_fiscal, MES_FIN_CALCULO, DIA_FIN_CALCULO).date()
    
    # 4. Obtener todos los registros de nómina utilizados para ese cálculo (Auditoría RNF-US-018)
    registros_nomina = Nomina.query.filter(
        Nomina.empleado == empleado,
        Nomina.fecha_inicio >= fecha_inicio_periodo,
        Nomina.fecha_fin <= fecha_fin_periodo
    ).order_by(Nomina.fecha_inicio.asc()).all()
    
    # Suma y promedio para mostrar la base del cálculo
    total_bruto = sum(n.salario_bruto for n in registros_nomina)
    meses_promedio = MESES_PROMEDIO # 12
    
    if registros_nomina:
        promedio_calculado = round(total_bruto / meses_promedio, 2)
    else:
        promedio_calculado = 0.0

    return render_template('aguinaldo/detalle_aguinaldo.html',
                           aguinaldo=aguinaldo,
                           empleado=empleado,
                           registros_nomina=registros_nomina,
                           total_bruto=total_bruto,
                           promedio_calculado=promedio_calculado,
                           periodo_inicio=fecha_inicio_periodo,
                           periodo_fin=fecha_fin_periodo)
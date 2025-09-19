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
        flash('No se encontró el empleado asociado a tu cuenta. Contacta al administrador.', 'danger')
        return redirect(url_for('registro_asistencia.ver_asistencia'))
    
    # Obtener la fecha y hora del servidor (RNF-SE-008 y RNF-AR-008)
    ahora = datetime.now()
    fecha_registro = ahora.date()
    hora_registro = ahora.time()

    # NUEVA LÓGICA: No permitir doble registro en 30 minutos
    # Busca el último registro de asistencia del empleado
    ultimo_registro = RegistroAsistencia.query.filter_by(
        Empleado_id_empleado=empleado.id_empleado
    ).order_by(RegistroAsistencia.fecha_registro.desc(), RegistroAsistencia.hora_salida.desc() if RegistroAsistencia.hora_salida is not None else RegistroAsistencia.hora_entrada.desc()).first()
    
    # Si hay un registro previo, se calcula el tiempo transcurrido
    if ultimo_registro:
        # Se determina el momento del último registro (entrada o salida)
        ultimo_momento = datetime.combine(
            ultimo_registro.fecha_registro,
            ultimo_registro.hora_salida if ultimo_registro.hora_salida else ultimo_registro.hora_entrada
        )
        tiempo_transcurrido = ahora - ultimo_momento
        
        # Se verifica si el tiempo transcurrido es menor a 30 minutos
        if tiempo_transcurrido < timedelta(minutes=30):
            flash('No puede registrar dos veces en menos de 30 minutos.', 'warning')
            return redirect(url_for('registro_asistencia.ver_asistencia'))

    try:
        # Lógica para MARCAR SALIDA
        registro_activo = RegistroAsistencia.query.filter_by(
            Empleado_id_empleado=empleado.id_empleado,
            fecha_registro=fecha_registro,
            hora_salida=None
        ).first()

        if registro_activo:
            registro_activo.hora_salida = hora_registro
            # ... (tu código para el cálculo de horas, monto, etc. se mantiene igual)
            # Asegúrate de que esta parte esté completa en tu archivo
            ...
            db.session.commit()
            flash('¡Salida registrada exitosamente!', 'success')
        
        # Lógica para MARCAR ENTRADA (FA1- Registro Duplicado)
        else:
            registro_de_entrada_hoy = RegistroAsistencia.query.filter_by(
                Empleado_id_empleado=empleado.id_empleado,
                fecha_registro=fecha_registro
            ).first()

            if registro_de_entrada_hoy:
                flash('Ya ha registrado su entrada para hoy. No se permite más de una entrada por día.', 'warning')
                return redirect(url_for('registro_asistencia.ver_asistencia'))

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
            flash('¡Entrada registrada exitosamente!', 'success')

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
    # Obtener todos los registros de asistencia ordenados por fecha
    registros = RegistroAsistencia.query.order_by(RegistroAsistencia.fecha_registro.desc()).all()
    return render_template('listar_asistencia.html', registros=registros)

# Editar registro de asistencia
@registro_asistencia_bp.route('/editar/<int:registro_id>', methods=['GET', 'POST'])
@permiso_requerido('editar_asistencia')
@login_required
def editar_asistencia(registro_id):
    registro = RegistroAsistencia.query.get_or_404(registro_id)

    if request.method == 'POST':
        try:
            registro.fecha_registro = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
            registro.hora_entrada = datetime.strptime(request.form['hora_entrada'], '%H:%M:%S').time()
            registro.hora_salida = datetime.strptime(request.form['hora_salida'], '%H:%M:%S').time()
            registro.aprobacion_registro = 'aprobado' in request.form
            
            # Recalcular todos los valores (total_horas, hora_extra, monto_pago)
            HORA_NOMINAL_ESTANDAR = 8.0
            dt_entrada = datetime.combine(registro.fecha_registro, registro.hora_entrada)
            dt_salida = datetime.combine(registro.fecha_registro, registro.hora_salida)

            if dt_salida < dt_entrada:
                dt_salida += timedelta(days=1)
            
            total_time_delta = dt_salida - dt_entrada
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
                # 1. Pago base del feriado (salario de un día normal, 8 horas)
                pago_base_feriado = HORA_NOMINAL_ESTANDAR * costo_por_hora_normal
                
                # 2. Pago adicional por las horas trabajadas en el feriado (al doble)
                pago_por_trabajar_feriado = registro.total_horas * costo_por_hora_feriado
                
                # 3. El monto total es la suma de ambos pagos
                registro.monto_pago = round(pago_base_feriado + pago_por_trabajar_feriado, 2)
                
                # Se ajustan las horas para reflejar que se trabajaron en un feriado
                registro.hora_feriado = registro.total_horas
                registro.hora_extra = 0
                horas_nominales_trabajadas = 0

            else:
                # Lógica para días normales y feriados de pago no obligatorio
                monto_pago = (horas_nominales_trabajadas * costo_por_hora_normal) + \
                            (registro.hora_extra * costo_por_hora_extra) + \
                            (registro.hora_feriado * costo_por_hora_feriado)
                registro.monto_pago = round(monto_pago, 2)

            db.session.commit()
            flash('Registro de asistencia actualizado exitosamente.', 'success')
            return redirect(url_for('registro_asistencia.listar_asistencia'))
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


# -------------------------  Generar Planilla Planilla 

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

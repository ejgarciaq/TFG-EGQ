from flask import Blueprint, current_app, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from payroll_app.models import db, Feriado, Empleado, Tipo_AP, Accion_Personal
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from payroll_app.routes.decorators import permiso_requerido

# Define the Blueprint
accion_personal_bp = Blueprint('accion_personal_bp', __name__)

# Define las extensiones de archivo permitidas
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    """Verifica si la extensión del archivo es permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calcular_dias_laborales(fecha_inicio, fecha_fin, dias_feriados):
    """
    Calcula los días laborables en un rango de fechas, excluyendo fines de semana y feriados.
    """
    dias_laborales = 0
    # Convertir las fechas de cadena a objetos datetime.date para la comparación
    feriados_set = {datetime.strptime(f, '%Y-%m-%d').date() for f in dias_feriados}
    
    if isinstance(fecha_inicio, str):
        fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    if isinstance(fecha_fin, str):
        fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()

    current_date = fecha_inicio
    while current_date <= fecha_fin:
        # 0 = lunes, 6 = domingo
        if current_date.weekday() < 5 and current_date not in feriados_set:
            dias_laborales += 1
        current_date += timedelta(days=1)
    return dias_laborales

# aprobar_accion --------------------------------------------------------------------------------------------------------------
@accion_personal_bp.route('/', methods=['GET', 'POST'])
@permiso_requerido('listar_accion_personal')
@login_required
def accion_personal():
    if request.method == 'POST':
        try:
            empleado_id = request.form.get('empleado_id')
            tipo_ap_id = request.form.get('tipo_ap_id')
            fecha_accion_str = request.form.get('fecha_accion')
            detalles = request.form.get('detalles')
            
            fecha_accion = datetime.strptime(fecha_accion_str, '%Y-%m-%d').date()

            fecha_inicio = None
            fecha_fin = None
            cantidad_dia = None
            
            empleado = Empleado.query.get(empleado_id)
            tipo_ap = Tipo_AP.query.get(tipo_ap_id)
            
            # Validaciones y lógica de cálculo para vacaciones e incapacidades
            if tipo_ap.nombre_tipo in ['Vacaciones', 'Incapacidad', 'Permiso c/ Goce de Salario']:
                fecha_inicio_str = request.form.get('fecha_inicio')
                fecha_fin_str = request.form.get('fecha_fin')
                
                if not fecha_inicio_str or not fecha_fin_str:
                    flash('Las fechas de inicio y fin son obligatorias para este tipo de acción.', 'danger')
                    return redirect(url_for('accion_personal_bp.accion_personal'))
                
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

                if fecha_inicio > fecha_fin:
                    flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'danger')
                    return redirect(url_for('accion_personal_bp.accion_personal'))
                
                # Obtener la lista de feriados para la función de cálculo
                dias_feriados_list = [f.fecha_feriado.strftime('%Y-%m-%d') for f in Feriado.query.all()]
                cantidad_dia = calcular_dias_laborales(fecha_inicio, fecha_fin, dias_feriados_list)
                
                # Validación de días de vacaciones disponibles
                if tipo_ap.nombre_tipo == 'Vacaciones':
                    if empleado.vacaciones_disponibles < cantidad_dia:
                        flash(f'Solicitud denegada: El empleado solo tiene {empleado.vacaciones_disponibles} días disponibles y está solicitando {cantidad_dia} días.', 'danger')
                        return redirect(url_for('accion_personal_bp.accion_personal'))
                    # Descontar días de vacaciones del saldo al momento de solicitar
                    # Esta lógica se puede mover a la aprobación para un control más estricto
                    empleado.vacaciones_disponibles -= cantidad_dia
                    db.session.add(empleado)

            # Lógica para cargar y guardar el archivo adjunto
            documento_adjunto = request.files.get('documento_adjunto')
            nombre_archivo = None
            
            if documento_adjunto and documento_adjunto.filename != '':
                if not allowed_file(documento_adjunto.filename):
                    flash('Tipo de archivo no permitido. Las extensiones válidas son: png, jpg, jpeg, pdf.', 'danger')
                    return redirect(url_for('accion_personal_bp.accion_personal'))
                
                fecha_formato = fecha_accion.strftime('%Y-%m-%d')
                
                nombre_empleado_sanitized = empleado.nombre_completo.replace(' ', '_').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
                nombre_tipo_sanitized = tipo_ap.nombre_tipo.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_')
                
                ext = os.path.splitext(secure_filename(documento_adjunto.filename))[1]
                nuevo_nombre = f"{fecha_formato}_{nombre_tipo_sanitized}_{nombre_empleado_sanitized}{ext}"
                nombre_archivo = nuevo_nombre
                
                app_root = os.path.dirname(os.path.abspath(__file__))
                upload_folder = os.path.join(app_root, '..', 'static', 'uploads')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                ruta_completa = os.path.join(upload_folder, nombre_archivo)
                documento_adjunto.save(ruta_completa)
            
            # Crear y guardar el registro en la base de datos
            nueva_accion = Accion_Personal(
                Empleado_id_empleado=empleado_id,
                Tipo_Ap_id_tipo_ap=tipo_ap_id,
                fecha_accion=fecha_accion,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                cantidad_dia=cantidad_dia,
                detalles=detalles,
                documento_adjunto=nombre_archivo,
                estado_ap=1 # Estado inicial: Pendiente
            )
            
            db.session.add(nueva_accion)
            db.session.commit()
            
            flash('Acción de personal registrada con éxito.', 'success')
            return redirect(url_for('accion_personal_bp.accion_personal'))

        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al registrar la acción: {e}', 'danger')
            return redirect(url_for('accion_personal_bp.accion_personal'))
    
    # Lógica para el método GET (muestra el formulario)
    else:
        is_admin = current_user.rol.tipo_rol == 'administrador'
        
        if is_admin:
            tipos_ap = Tipo_AP.query.all()
            empleados_para_form = Empleado.query.all()
            vacaciones_disponibles = 'N/A'
        else:
            allowed_types = ['Incapacidad', 'Vacaciones', 'Permiso c/ Goce de Salario', 'Permiso s/ Goce de Salario', 'Renuncia']
            tipos_ap = Tipo_AP.query.filter(Tipo_AP.nombre_tipo.in_(allowed_types)).all()
            empleados_para_form = [current_user.empleado] if current_user.empleado else []
            vacaciones_disponibles = current_user.empleado.vacaciones_disponibles if current_user.empleado else 0
        
        dias_feriados = [f.fecha_feriado.strftime('%Y-%m-%d') for f in Feriado.query.all()]
        
        return render_template('accion_personal.html', 
                               empleados=empleados_para_form, 
                               tipos_ap=tipos_ap, 
                               dias_feriados=dias_feriados,
                               vacaciones_disponibles=vacaciones_disponibles)

# historial usuario de acciones de personal ----------------------------------------------------------------

@accion_personal_bp.route('/ver_historial', methods=['GET'])
@permiso_requerido('listar_accion_personal')
@login_required
def ver_historial_apu():
    page = request.args.get('page', 1, type=int)
    is_admin = current_user.rol.tipo_rol == 'administrador'
    
    query = Accion_Personal.query.order_by(Accion_Personal.fecha_accion.desc())

    if not is_admin:
        if current_user.empleado:
            query = query.filter_by(Empleado_id_empleado=current_user.empleado.id_empleado) # Corregido
        else:
            flash('Tu cuenta no está asociada a un empleado. No puedes ver tu historial.', 'warning')
            query = query.filter_by(Empleado_id_empleado=-1) # No resultados

    # Paginar los resultados
    pagination = db.paginate(query, page=page, per_page=15, error_out=False)
    
    # Renderizar la plantilla del historial, pasando la paginación
    return render_template('historial_apu.html', pagination=pagination)

# aprobacion de accesos administrativos-------------------------------------------------------
@accion_personal_bp.route('/historial')
@login_required
@permiso_requerido('admin_accion_personal')
def acciones_administrativas():
    """
    Muestra el historial de acciones de personal con paginación
    """
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    paginated_acciones = Accion_Personal.query.order_by(Accion_Personal.fecha_accion.desc()).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    return render_template('historial_acciones.html', 
                            pagination=paginated_acciones)


# aprobar_accion --------------------------------------------------------------------------------------------------------------
@accion_personal_bp.route('/aprobar_accion/<int:ap_id>', methods=['POST'])
@permiso_requerido('aprobar_acciones_personales')
@login_required
def aprobar_accion(ap_id):
    """
    Aprueba una acción de personal si el usuario tiene el permiso requerido.
    El decorador 'permiso_requerido' se encarga de la validación.
    """
    ap = Accion_Personal.query.get_or_404(ap_id)
    
    if ap.estado_ap != 1:
        flash('Esta acción ya ha sido procesada.', 'warning')
        return redirect(url_for('accion_personal_bp.accion_personal'))

    try:
        ap.estado_ap = 2 
        ap.id_aprobador = current_user.id_usuario
        ap.fecha_aprobacion = datetime.utcnow()

        VACACIONES_ID = 6
        INCAPACIDAD_ID = 5

        if ap.Tipo_Ap_id_tipo_ap in [VACACIONES_ID, INCAPACIDAD_ID]:
            empleado = Empleado.query.get(ap.Empleado_id_empleado)
            if empleado:
                empleado.estado = 2 
                db.session.add(empleado)
                flash(f'El estado del empleado {empleado.nombre_completo} ha sido actualizado a "Inactivo Temporalmente".', 'info')
        
        db.session.commit()
        flash('Acción de personal aprobada y registrada exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al aprobar la acción: {str(e)}', 'danger')
    
    return redirect(url_for('accion_personal_bp.acciones_administrativas'))

# Rechazar accion de personal ----------------------------------------------------------
@accion_personal_bp.route('/rechazar_accion/<int:ap_id>', methods=['POST'])
@permiso_requerido('rechazar_acciones_personales')
@login_required
def rechazar_accion(ap_id):
    """
    Rechaza una acción de personal si el usuario tiene el permiso requerido.
    """
    ap = Accion_Personal.query.get_or_404(ap_id)
    
    ap.estado_ap = 3
    ap.id_aprobador = current_user.id_usuario
    ap.fecha_aprobacion = datetime.utcnow()
    
    try:
        db.session.commit()
        flash('Acción de personal rechazada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al rechazar la acción: {str(e)}', 'danger')

    return redirect(url_for('accion_personal_bp.acciones_administrativas'))

# eliminar accion de personal -----------------------------------------------

@accion_personal_bp.route('/eliminar_accion/<int:ap_id>', methods=['POST'])
@login_required
@permiso_requerido('eliminar_accion_personal')
def eliminar_accion(ap_id):
    """
    Elimina una acción de personal de la base de datos.
    Requiere el permiso 'eliminar_acciones_personales'.
    """
    ap = Accion_Personal.query.get_or_404(ap_id)
    
    try:
        db.session.delete(ap)
        db.session.commit()
        flash('Acción de personal eliminada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al eliminar la acción: {str(e)}', 'danger')
        
    return redirect(url_for('accion_personal_bp.acciones_administrativas'))
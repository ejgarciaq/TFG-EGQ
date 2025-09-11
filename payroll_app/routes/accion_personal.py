from flask import Blueprint, current_app, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from payroll_app.models import db, Feriado, Empleado, Tipo_AP, Accion_Personal
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from payroll_app.routes.decorators import permiso_requerido

# Define the Blueprint. The static folder is handled in the main app's __init__.py file
accion_personal_bp = Blueprint('accion_personal_bp', __name__)

# Define las extensiones de archivo permitidas
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    """
    Verifica si la extensión del archivo es permitida.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
            
            fecha_inicio_str = request.form.get('fecha_inicio')
            fecha_fin_str = request.form.get('fecha_fin')
            
            if fecha_inicio_str and fecha_fin_str:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
                
                delta = fecha_fin - fecha_inicio
                cantidad_dia = delta.days + 1
            
            documento_adjunto = request.files.get('documento_adjunto')
            nombre_archivo = None
            
            if documento_adjunto and documento_adjunto.filename != '':
                # Valida la extensión del archivo
                if not allowed_file(documento_adjunto.filename):
                    flash('Tipo de archivo no permitido. Las extensiones válidas son: pdf, docx, xlsx, png, jpg, jpeg, gif.', 'danger')
                    return redirect(url_for('accion_personal_bp.accion_personal'))
                
                # Lógica para sanitizar y guardar el archivo
                empleado = Empleado.query.get(empleado_id)
                tipo_ap = Tipo_AP.query.get(tipo_ap_id)
                
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
                estado_ap=1
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
            acciones_personales = Accion_Personal.query.order_by(Accion_Personal.fecha_accion.desc()).all()
        else:
            allowed_types = ['Incapacidad', 'Vacaciones', 'Permiso c/ Goce de Salario', 'Permiso s/ Goce de Salario', 'Renuncia']
            tipos_ap = Tipo_AP.query.filter(Tipo_AP.nombre_tipo.in_(allowed_types)).all()
            empleados_para_form = [current_user.empleado] if current_user.empleado else []
            acciones_personales = Accion_Personal.query.filter_by(Empleado_id_empleado=current_user.empleado.id_empleado).order_by(Accion_Personal.fecha_accion.desc()).all()

        dias_feriados = [f.fecha_feriado.strftime('%Y-%m-%d') for f in Feriado.query.all()]
        
        return render_template('accion_personal.html', 
                               empleados=empleados_para_form, 
                               tipos_ap=tipos_ap, 
                               dias_feriados=dias_feriados,
                               acciones_personales=acciones_personales)
    
    
# historial usuario de acciones de personal ----------------------------------------------------------------

@accion_personal_bp.route('/ver_historial', methods=['GET'])
#@permiso_requerido('ver_historial_acciones')
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
    pagination = db.paginate(query, page=page, per_page=10, error_out=False)
    
    # Renderizar la plantilla del historial, pasando la paginación
    return render_template('historial_apu.html', pagination=pagination)











































# aprobar_accion Apebación--------------------------------------------------------------------------------------------------------------
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
    
    return redirect(url_for('accion_personal_bp.accion_personal'))

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

    return redirect(url_for('accion_personal_bp.accion_personal'))

# eliminar accion de personal
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
        
    return redirect(url_for('accion_personal_bp.accion_personal'))

# Nueva ruta para el historial
@accion_personal_bp.route('/historial')
@login_required
#@permiso_requerido('ver_historial_acciones')
def ver_historial():
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



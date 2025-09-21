from flask import Blueprint, current_app, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from payroll_app.models import db, Feriado, Empleado, Tipo_AP, Accion_Personal
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from payroll_app.routes.decorators import permiso_requerido
from flask_mail import Message
from threading import Thread


# Define the Blueprint
accion_personal_bp = Blueprint('accion_personal_bp', __name__)

# Define las extensiones de archivo permitidas
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    """Verifica si la extensión del archivo es permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_async_email(app, msg):
    # Funcion que envía el correo en un hilo separado
    with app.app_context():
        # Obtenemos la instancia de Flask-Mail del objeto app
        mail_instance = app.extensions.get('mail')
        if mail_instance:
            try:
                mail_instance.send(msg)
                app.logger.info(f"Correo enviado exitosamente a: {msg.recipients[0]}")
            except Exception as e:
                            app.logger.error(f"Error al enviar correo a {msg.recipients[0]}: {e}", exc_info=True)
        else:
            app.logger.error("Error: Flask-Mail no está inicializado en el hilo.")


def enviar_notificacion_por_correo(destinatario, asunto, cuerpo):
    """
    Crea y lanza un hilo para enviar un correo electrónico.
    """
    try:
        app = current_app._get_current_object()
        msg = Message(
            asunto,
            sender=app.config['MAIL_USERNAME'],
            recipients=[destinatario],
            body=cuerpo
        )
        
        # Crea y lanza el hilo para enviar el correo en segundo plano
        thr = Thread(target=send_async_email, args=[app, msg])
        thr.start()

        app.logger.info(f"Hilo de envío de correo a {destinatario} iniciado.")
        return True
    except Exception as e:
        current_app.logger.error(f"Error al iniciar el hilo de correo a {destinatario}: {e}", exc_info=True)
        return False
    

# accion de personal --------------------------------------------------------------------------------------------------------------
@accion_personal_bp.route('/', methods=['GET', 'POST'])
@permiso_requerido('listar_accion_personal')
@login_required
def accion_personal():
    if request.method == 'POST':
        try:
            empleado_id = request.form.get('empleado_id')
            tipo_ap_id = request.form.get('tipo_ap_id')
            detalles = request.form.get('detalles')
            
            fecha_accion = datetime.utcnow().date()
            
            empleado = Empleado.query.get(empleado_id)
            tipo_ap = Tipo_AP.query.get(tipo_ap_id)
            
            if not empleado or not tipo_ap:
                flash('Empleado o tipo de acción no válido.', 'danger')
                return redirect(url_for('accion_personal_bp.accion_personal'))

            fecha_inicio = None
            fecha_fin = None
            cantidad_dia = None
            
            if tipo_ap.nombre_tipo in ['Vacaciones', 'Permiso c/ Goce de Salario', 'Permiso s/ Goce de Salario']:
                fecha_inicio_str = request.form.get('fecha_inicio')
                fecha_fin_str = request.form.get('fecha_fin')
                cantidad_dia_str = request.form.get('cantidad_dia_vac')
                
            elif tipo_ap.nombre_tipo == 'Incapacidad':
                fecha_inicio_str = request.form.get('fecha_inicio_inc')
                fecha_fin_str = request.form.get('fecha_fin_inc')
                cantidad_dia_str = request.form.get('cantidad_dia_inc')
            
            if tipo_ap.nombre_tipo in ['Vacaciones', 'Incapacidad', 'Permiso c/ Goce de Salario']:
                if not fecha_inicio_str or not fecha_fin_str:
                    flash('Las fechas de inicio y fin son obligatorias para este tipo de acción.', 'danger')
                    return redirect(url_for('accion_personal_bp.accion_personal'))
                
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            
                if fecha_inicio > fecha_fin:
                    flash('La fecha de fin no puede ser anterior a la fecha de inicio.', 'danger')
                    return redirect(url_for('accion_personal_bp.accion_personal'))
            
            if cantidad_dia_str:
                cantidad_dia = int(cantidad_dia_str)

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
            
            correo_admin = 'edson.garcia.cr@outlook.com'
            asunto_admin = f'Nueva Solicitud de {tipo_ap.nombre_tipo} Pendiente'
            cuerpo_admin = f'Una nueva solicitud de {tipo_ap.nombre_tipo} de {empleado.nombre_completo} ha sido enviada. Por favor, revísela.'
            enviar_notificacion_por_correo(correo_admin, asunto_admin, cuerpo_admin)

            asunto_empleado = f'Confirmación de Solicitud de {tipo_ap.nombre_tipo}'
            cuerpo_empleado = f'Hola {empleado.nombre_completo}, tu solicitud de {tipo_ap.nombre_tipo} ha sido enviada con éxito y está pendiente de aprobación.'
            enviar_notificacion_por_correo(empleado.correo, asunto_empleado, cuerpo_empleado)
            
            current_app.logger.info(f'Nueva acción de personal para el empleado {empleado.id_empleado} registrada con éxito.')
            flash('Acción de personal registrada con éxito.', 'success')
            return redirect(url_for('accion_personal_bp.accion_personal'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Error al registrar la acción de personal: {e}', exc_info=True)
            flash(f'Ocurrió un error al registrar la acción: {e}', 'danger')
            return redirect(url_for('accion_personal_bp.accion_personal'))
    
    else: 
        is_admin = current_user.rol.tipo_rol == 'administrador'
        
        if is_admin:
            tipos_ap = Tipo_AP.query.all()
            empleados_para_form = Empleado.query.all()
        else:
            allowed_types = ['Incapacidad', 'Vacaciones', 'Permiso c/ Goce de Salario', 'Permiso s/ Goce de Salario', 'Renuncia']
            tipos_ap = Tipo_AP.query.filter(Tipo_AP.nombre_tipo.in_(allowed_types)).all()
            empleados_para_form = [current_user.empleado] if current_user.empleado else []
        
        dias_feriados = [f.fecha_feriado.strftime('%Y-%m-%d') for f in Feriado.query.all()]
        
        return render_template('accion_personal.html', 
                               empleados=empleados_para_form, 
                               tipos_ap=tipos_ap, 
                               dias_feriados=dias_feriados,
                               fecha_accion_actual=datetime.utcnow().date())

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
    pagination = db.paginate(query, page=page, per_page=10, error_out=False)
    
    # Renderizar la plantilla del historial, pasando la paginación
    return render_template('historial_apu.html', pagination=pagination)

# aprobacion de accesos administrativos-------------------------------------------------------
@accion_personal_bp.route('/historial')
@login_required
@permiso_requerido('aprobar_acciones_personales')
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
    # Obtiene el número de página del formulario. Usa 1 como valor por defecto.
    page = request.form.get('page', 1, type=int)

    ap = Accion_Personal.query.get_or_404(ap_id)
    
    if ap.estado_ap != 1:
        flash('Esta acción ya ha sido procesada.', 'warning')
        return redirect(url_for('accion_personal_bp.acciones_administrativas', page=page))

    try:
        ap.estado_ap = 2 
        ap.id_aprobador = current_user.id_usuario
        ap.fecha_aprobacion = datetime.utcnow()
        
        if ap.tipo_ap.nombre_tipo == 'Vacaciones':
            empleado = ap.empleado
            if empleado and ap.cantidad_dia:
                empleado.vacaciones_disponibles -= ap.cantidad_dia
                db.session.add(empleado)
                flash(f'Se han descontado {ap.cantidad_dia} días de vacaciones al empleado {empleado.nombre_completo}.', 'info')
        
        db.session.commit()

        # --- CÓDIGO AÑADIDO: Notificación de aprobación por correo ---
        empleado = ap.empleado
        asunto_aprobacion = f'Actualización de Solicitud de {ap.tipo_ap.nombre_tipo}'
        cuerpo_aprobacion = f'Hola {empleado.nombre_completo}, tu solicitud de {ap.tipo_ap.nombre_tipo} ha sido aprobada.'
        enviar_notificacion_por_correo(empleado.correo, asunto_aprobacion, cuerpo_aprobacion)
        # -------------------------------------------------------------

        flash('Acción de personal aprobada y registrada exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al aprobar la acción: {str(e)}', 'danger')
    
    # Redirige a la página correcta
    return redirect(url_for('accion_personal_bp.acciones_administrativas', page=page))

# Rechazar accion de personal ----------------------------------------------------------
@accion_personal_bp.route('/rechazar_accion/<int:ap_id>', methods=['POST'])
@permiso_requerido('rechazar_acciones_personales')
@login_required
def rechazar_accion(ap_id):
    # Obtiene el número de página del formulario. Usa 1 como valor por defecto.
    page = request.form.get('page', 1, type=int)

    ap = Accion_Personal.query.get_or_404(ap_id)
    
    try:
        ap.estado_ap = 3
        ap.id_aprobador = current_user.id_usuario
        ap.fecha_aprobacion = datetime.utcnow()
        
        db.session.commit()
        
        empleado = ap.empleado
        asunto_rechazo = f'Actualización de Solicitud de {ap.tipo_ap.nombre_tipo}'
        cuerpo_rechazo = f'Hola {empleado.nombre_completo}, tu solicitud de {ap.tipo_ap.nombre_tipo} ha sido rechazada.'
        enviar_notificacion_por_correo(empleado.correo, asunto_rechazo, cuerpo_rechazo)

        flash('Acción de personal rechazada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al rechazar la acción: {str(e)}', 'danger')

    # Redirige a la página correcta
    return redirect(url_for('accion_personal_bp.acciones_administrativas', page=page))
# eliminar accion de personal -----------------------------------------------

@accion_personal_bp.route('/eliminar_accion/<int:ap_id>', methods=['POST'])
@login_required
@permiso_requerido('eliminar_accion_personal')
def eliminar_accion(ap_id):
    """
    Elimina una acción de personal de la base de datos.
    """
    # Obtiene el número de página del formulario. Usa 1 como valor por defecto.
    page = request.form.get('page', 1, type=int)

    ap = Accion_Personal.query.get_or_404(ap_id)
    
    try:
        db.session.delete(ap)
        db.session.commit()
        flash('Acción de personal eliminada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al eliminar la acción: {str(e)}', 'danger')
        
    # Redirige a la página correcta
    return redirect(url_for('accion_personal_bp.acciones_administrativas', page=page))


@accion_personal_bp.route('/ver_detalle/<int:ap_id>')
@permiso_requerido('listar_accion_personal')
@login_required
def ver_detalle_ap(ap_id):
    """
    Muestra los detalles completos de una acción de personal específica.
    """
    accion = Accion_Personal.query.get_or_404(ap_id)
    return render_template('detalle_ap.html', accion=accion)
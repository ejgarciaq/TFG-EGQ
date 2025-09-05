from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from payroll_app.models import db, Feriado, Empleado, Tipo_AP, Accion_Personal
from datetime import datetime
import os
from werkzeug.utils import secure_filename

# El nombre del blueprint es 'accion_personal_bp'
accion_personal_bp = Blueprint('accion_personal_bp', __name__)

# Configuración de la carpeta de subida de documentos
UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads'))
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Extensiones de archivo permitidas
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'doc', 'docx', 'xlsx', 'txt'}

def allowed_file(filename):
    """Función para validar la extensión del archivo."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@accion_personal_bp.route('/accion_personal', methods=['GET', 'POST'])
@login_required
def accion_personal():
    empleados = Empleado.query.all()
    tipos_ap = Tipo_AP.query.all()
    acciones_personales = Accion_Personal.query.order_by(Accion_Personal.fecha_accion.desc()).all()

    dias_feriados = [f.fecha_feriado.strftime('%Y-%m-%d') for f in Feriado.query.all()]
    
    if request.method == 'POST':
        try:
            empleado_id = request.form.get('empleado_id')
            tipo_ap_id = request.form.get('tipo_ap_id')
            fecha_accion_str = request.form.get('fecha_accion')
            detalles = request.form.get('detalles')
            
            cantidad_dia_str = request.form.get('cantidad_dia')
            cantidad_dia = int(cantidad_dia_str) if cantidad_dia_str else None
            
            fecha_inicio_str = request.form.get('fecha_inicio')
            fecha_fin_str = request.form.get('fecha_fin')
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d') if fecha_inicio_str else None
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d') if fecha_fin_str else None
            
            file = request.files.get('documento_adjunto')
            filename = None
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                try:
                    file.save(file_path)
                except Exception as e:
                    flash(f'Error al guardar el archivo: {str(e)}', 'danger')
                    return redirect(url_for('accion_personal_bp.accion_personal'))
            
            nueva_ap = Accion_Personal(
                Empleado_id_empleado=empleado_id,
                Tipo_Ap_id_tipo_ap=tipo_ap_id,
                fecha_accion=datetime.strptime(fecha_accion_str, '%Y-%m-%d'),
                detalles=detalles,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                cantidad_dia=cantidad_dia,
                documento_adjunto=filename,
                estado_ap=1
            )
            
            db.session.add(nueva_ap)
            db.session.commit()
            flash('Acción de personal registrada exitosamente.', 'success')
            return redirect(url_for('accion_personal_bp.accion_personal'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al registrar la acción de personal: {str(e)}', 'danger')

    return render_template('accion_personal.html', 
                            empleados=empleados, 
                            tipos_ap=tipos_ap, 
                            acciones_personales=acciones_personales,
                            dias_feriados=dias_feriados)


@accion_personal_bp.route('/aprobar_accion/<int:ap_id>', methods=['POST'])
@login_required
def aprobar_accion(ap_id):
    ap = Accion_Personal.query.get_or_404(ap_id)
    
    if current_user.rol.tipo_rol not in ['gestor', 'admin']:
        flash('No tienes permiso para aprobar acciones de personal.', 'danger')
        return redirect(url_for('accion_personal_bp.accion_personal'))
    
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

@accion_personal_bp.route('/rechazar_accion/<int:ap_id>', methods=['POST'])
@login_required
def rechazar_accion(ap_id):
    ap = Accion_Personal.query.get_or_404(ap_id)
    
    if current_user.rol.tipo_rol in ['gestor', 'admin']:
        ap.estado_ap = 3 
        ap.id_aprobador = current_user.id_usuario
        ap.fecha_aprobacion = datetime.utcnow()
        
        try:
            db.session.commit()
            flash('Acción de personal rechazada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al rechazar la acción: {str(e)}', 'danger')
    else:
        flash('No tienes permiso para rechazar acciones de personal.', 'danger')
    
    return redirect(url_for('accion_personal_bp.accion_personal'))
# En payroll_app/routes/admin.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from payroll_app.models import db, Configuracion 
from payroll_app.routes.decorators import permiso_requerido
from payroll_app.utils import cargar_configuracion
from datetime import datetime

# Definición del Blueprint.
config_bp = Blueprint('config', __name__, url_prefix='/auth/configuracion') 

@config_bp.route('/', methods=['GET', 'POST'])
@permiso_requerido('parametros')  # Usar el decorador de permisos
@login_required # Proteger esta ruta de acceso no autorizado
def administrar_configuracion():
    # 1. Obtener todos los objetos de la BD
    parametros = Configuracion.query.order_by(Configuracion.nombre_parametro).all()
    
    # 2. Cargar el diccionario (config_dict)
    config_dict = cargar_configuracion() 
    
    if request.method == 'POST':
        try:
            for param in parametros:
                nuevo_valor_raw = request.form.get(param.nombre_parametro)
                
                if nuevo_valor_raw is None:
                    nuevo_valor = ''
                else:
                    nuevo_valor = nuevo_valor_raw.strip()
                
                # *** CAMBIO CLAVE AQUÍ: usar valor_parametro ***
                valor_actual_str = param.valor_parametro if param.valor_parametro is not None else ''
                
                if nuevo_valor != valor_actual_str:
                    
                    if not nuevo_valor and param.tipo_dato != 'json':
                        # Asignamos el valor corregido
                        param.valor_parametro = None if param.tipo_dato in ['float', 'int'] else nuevo_valor
                    else:
                        # Asignamos el valor corregido
                        param.valor_parametro = nuevo_valor

                    # Si el valor cambió, actualizamos el timestamp
                    param.fecha_actualizacion = datetime.utcnow()
                    
            db.session.commit()
            
            flash('Configuración actualizada exitosamente.', 'success')
            return redirect(url_for('config.administrar_configuracion'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la configuración: {str(e)}', 'danger')
            
    return render_template('configuracion/configuracion.html', 
                            parametros=parametros,
                            config_dict=config_dict)
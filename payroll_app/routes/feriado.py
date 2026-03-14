from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from payroll_app.models import db, Feriado
from datetime import date, datetime
from payroll_app.routes.decorators import permiso_requerido
import holidays as pyholidays
""" Rutas para gestionar feriados en la aplicación de nómina."""
feriado_bp = Blueprint('feriado', __name__)

""" Muestra una lista paginada de todos los feriados. """
@feriado_bp.route('/listar_feriado')
@permiso_requerido('listar_feriado')
@login_required
def listar_feriados():
    """Muestra una lista paginada de todos los feriados."""
    # Obtiene el número de página de la URL, por defecto es 1
    page = request.args.get('page', 1, type=int)
    # Define el número de registros por página (ej. 10)
    per_page = 12 
    # Crea la consulta base, ordenada por fecha de forma ascendente
    query = Feriado.query.order_by(Feriado.fecha_feriado.desc())
    # Aplica la paginación a la consulta
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template('feriado/feriado.html', pagination=pagination)

""" Crea un nuevo feriado a la base de datos. """
@feriado_bp.route('/agregar_feriados', methods=['POST'])
@permiso_requerido('crear_feriados')
@login_required
def agregar_feriado():
    fecha_str = request.form.get('fecha_feriado')
    descripcion = request.form.get('descripcion_feriado')
    pago_obligatorio_str = request.form.get('pago_obligatorio')
    pago_obligatorio = True if pago_obligatorio_str == 'on' else False

    if not fecha_str or not descripcion:
        flash('Por favor, ingresa una fecha y una descripción para el feriado.', 'danger')
        return redirect(url_for('feriado.listar_feriados'))

    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        feriado_existente = Feriado.query.filter_by(fecha_feriado=fecha).first()
        if feriado_existente:
            flash(f'El feriado en la fecha {fecha_str} ya existe.', 'warning')
            return redirect(url_for('feriado.listar_feriados'))

        nuevo_feriado = Feriado(fecha_feriado=fecha, descripcion_feriado=descripcion, pago_obligatorio=pago_obligatorio)
        db.session.add(nuevo_feriado)
        db.session.commit()
        flash('Feriado agregado exitosamente.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al agregar el feriado: {e}', 'danger')

    return redirect(url_for('feriado.listar_feriados'))

""" Edite un feriado existente en la base de datos. """
@feriado_bp.route('/editar_feriado/<int:id_feriado>', methods=['GET', 'POST'])
@permiso_requerido('editar_feriado')
@login_required
def editar_feriado(id_feriado):
    feriado = Feriado.query.get_or_404(id_feriado)
    if request.method == 'POST':
        try:
            feriado.fecha_feriado = datetime.strptime(request.form.get('fecha_feriado'), '%Y-%m-%d').date()
            feriado.descripcion_feriado = request.form.get('descripcion_feriado')
            pago_obligatorio_str = request.form.get('pago_obligatorio')
            feriado.pago_obligatorio = True if pago_obligatorio_str == 'on' else False
            
            db.session.commit()
            flash('Feriado actualizado exitosamente.', 'success')
            return redirect(url_for('feriado.listar_feriados'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al editar el feriado: {e}', 'danger')
    
    return render_template('feriado/editar_feriado.html', feriado=feriado)

""" Elimina un feriado de la base de datos. """
@feriado_bp.route('/eliminar_feriado/<int:id_feriado>', methods=['POST'])
@permiso_requerido('eliminar_feriado')
@login_required
def eliminar_feriado(id_feriado):
    feriado = Feriado.query.get_or_404(id_feriado)
    try:
        db.session.delete(feriado)
        db.session.commit()
        flash('Feriado eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al eliminar el feriado: {e}', 'danger')
        
    return redirect(url_for('feriado.listar_feriados'))

""" Agrega los feriados del año actual, validando que no existan. """
@feriado_bp.route('/agregar_feriados_siguiente_mes', methods=['POST'])
@permiso_requerido('listar_feriado')
@login_required
def agregar_feriados_año_actual():
    today = date.today()
    current_year = today.year 
    
    cr_holidays = pyholidays.CountryHoliday('CR', years=current_year)

    feriados_agregados = 0
    feriados_existentes = 0

    for feriado_date, feriado_name in cr_holidays.items():
        # Validar que el feriado no exista en la base de datos
        feriado_existente = Feriado.query.filter_by(fecha_feriado=feriado_date).first()

        if feriado_existente:
            feriados_existentes += 1
        else:
            # Si no existe, crear un nuevo registro y agregarlo
            nuevo_feriado = Feriado(
                fecha_feriado=feriado_date,
                descripcion_feriado=feriado_name, # Asegúrate de que el campo sea 'descripcion_feriado' si así lo tienes en tu modelo Feriado
                pago_obligatorio=False # Asume un valor por defecto
            )
            db.session.add(nuevo_feriado)
            feriados_agregados += 1
    
    # Guardar todos los nuevos feriados en la base de datos
    try:
        db.session.commit()
        if feriados_agregados > 0:
            flash(f"Se agregaron {feriados_agregados} feriados para el año actual. {feriados_existentes} ya existían.", "success")
        else:
            flash(f"No se agregaron nuevos feriados. Todos los feriados del año actual ya existen.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Ocurrió un error al agregar los feriados: {e}", "danger")

    # Redirigir a la lista de feriados con paginación
    page = request.args.get('page', 1, type=int)
    return redirect(url_for('feriado.listar_feriados', page=page))

""" Agrega los feriados del próximo año, validando que no existan. """
@feriado_bp.route('/agregar_feriados_proximo_año', methods=['POST'])
@permiso_requerido('listar_feriado')
@login_required
def agregar_feriados_proximo_año():
    today = date.today() 
    #  Calcula el año objetivo como el año actual + 1
    target_year = today.year + 1 
    #  pyholidays SOLO te devolverá los feriados para 'target_year'
    cr_holidays = pyholidays.CountryHoliday('CR', years=target_year)

    feriados_agregados = 0
    feriados_existentes = 0

    # Al iterar sobre cr_holidays, SOLO procesas los feriados del 'target_year'
    for feriado_date, feriado_name in cr_holidays.items():
        # 1. Validar que el feriado no exista en la base de datos
        # Esto previene duplicados para el MISMO feriado en el MISMO año
        feriado_existente = Feriado.query.filter_by(fecha_feriado=feriado_date).first()

        if feriado_existente:
            feriados_existentes += 1
        else:
            # 2. Si no existe, crear un nuevo registro y agregarlo
            nuevo_feriado = Feriado(
                fecha_feriado=feriado_date,
                descripcion_feriado=feriado_name,
            )
            db.session.add(nuevo_feriado)
            feriados_agregados += 1
    
    # 3. Guardar todos los nuevos feriados en la base de datos
    try:
        db.session.commit()
        if feriados_agregados > 0:
            flash(f"Se agregaron {feriados_agregados} feriados para el año {target_year}. {feriados_existentes} ya existían.", "success")
        else:
            flash(f"No se agregaron nuevos feriados para el año {target_year}. Todos ya existen.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Ocurrió un error al agregar los feriados: {e}", "danger")

    # 4. Redirigir a la lista de feriados con paginación
    page = request.args.get('page', 1, type=int)
    return redirect(url_for('feriado.listar_feriados', page=page))
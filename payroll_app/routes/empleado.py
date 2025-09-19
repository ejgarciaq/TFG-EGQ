import re
import secrets
import string
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
from werkzeug.security import generate_password_hash
from payroll_app.models import (
    db,
    Usuario,
    Rol,
    Empleado,
    Puesto,
    RegistroAsistencia,
    Nomina,
    TipoNomina,
)
from datetime import datetime
from flask_login import login_required, current_user
from payroll_app.routes.decorators import permiso_requerido
import logging

# Se crea un objeto Blueprint llamado 'empleado', que permite modularizar la aplicación Flask.
empleado_bp = Blueprint("empleado", __name__, template_folder="templates")

@empleado_bp.route("/crear_empleado", methods=["GET", "POST"])
@permiso_requerido('crear_empleado')
@login_required
def crear_empleado():
    roles = Rol.query.all()
    puestos = Puesto.query.all()
    tipos_nomina = TipoNomina.query.all()

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        correo = request.form["correo"]
        telefono = request.form["telefono"]
        cedula = request.form["cedula"]

        # Validaciones con expresiones regulares
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        phone_regex = r"^[0-9]{8}$"
        password_regex = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+-.,/])[A-Za-z\d!@#$%^&*()_+-.,/]{8,}$"

        # Se agregan todas las validaciones de duplicidad
        if Empleado.query.filter_by(cedula=cedula).first():
            flash("Ya existe un empleado con esa cédula en el sistema.", "danger")
            return redirect(url_for("empleado.crear_empleado"))
        
        if Usuario.query.filter_by(username=username).first():
            flash("El nombre de usuario ya existe. Por favor, elige otro.", "danger")
            return redirect(url_for("empleado.crear_empleado"))
        
        # Validación para correo duplicado
        if Empleado.query.filter_by(correo=correo).first():
            flash("Ya existe un empleado con ese correo electrónico en el sistema.", "danger")
            return redirect(url_for("empleado.crear_empleado"))

        if not re.match(email_regex, correo):
            flash(
                "El formato del correo electrónico no es válido. ejemplo@correo.com",
                "danger",
            )
            return redirect(url_for("empleado.crear_empleado"))

        if not re.match(phone_regex, telefono):
            flash(
                "El número de teléfono debe contener exactamente 8 dígitos.", "danger"
            )
            return redirect(url_for("empleado.crear_empleado"))

        if not re.match(password_regex, password):
            flash(
                "La nueva contraseña no cumple con los requisitos: <br>- Mínimo 8 caracteres.<br>- Al menos una mayúscula.<br>- Al menos una minúscula.<br>- Al menos un número.<br>- Al menos un símbolo.",
                "danger",
            )
            return redirect(url_for("empleado.crear_empleado"))

        try:
            hashed_password = generate_password_hash(password)
            nuevo_usuario = Usuario(
                username=username,
                password=hashed_password,
                estado_usuario=True,
                Rol_id_rol=request.form["rol_id"],
            )

            fecha_ingreso = datetime.strptime(
                request.form["fecha_ingreso"], "%Y-%m-%d"
            ).date()

            tipo_nomina_id = request.form["tipo_nomina_id"]

            nuevo_empleado = Empleado(
                nombre=request.form["nombre"],
                apellido_primero=request.form["apellido_primero"],
                apellido_segundo=request.form.get("apellido_segundo"),
                cedula=cedula,
                correo=correo,
                telefono=telefono,
                fecha_ingreso=fecha_ingreso,
                fecha_salida=None,
                salario_base=float(request.form["salario_base"]),
                estado_empleado=True,
                Puesto_id_puesto=request.form["puesto_id"],
                TipoNomina_id_tipo_nomina=tipo_nomina_id,
                usuario=nuevo_usuario,
            )

            db.session.add(nuevo_empleado)
            db.session.commit()

            flash("Empleado creado exitosamente.", "success")
            return redirect(url_for("empleado.listar_empleado"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error al crear el empleado: {str(e)}", "danger")
            return render_template(
                "crear_empleado.html",
                puestos=puestos,
                roles=roles,
                tipos_nomina=tipos_nomina,
            )

    return render_template(
        "crear_empleado.html", puestos=puestos, roles=roles, tipos_nomina=tipos_nomina
    )

# ---------------------------------------------------------------------------------

@empleado_bp.route("/editar_empleado/<int:id>", methods=["GET", "POST"])
@permiso_requerido('editar_emplado')
@login_required
def editar_empleado(id):
    empleado = Empleado.query.get_or_404(id)
    roles = Rol.query.all()
    puestos = Puesto.query.all()
    tipos_nomina = TipoNomina.query.all()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "guardar_cambios":
            try:
                # Obtener los datos del formulario
                username = request.form["username"]
                nombre = request.form["nombre"]
                apellido_primero = request.form["apellido_primero"]
                apellido_segundo = request.form.get("apellido_segundo")
                cedula = request.form["cedula"]
                correo = request.form["correo"]
                telefono = request.form["telefono"]
                salario_base_str = request.form["salario_base"]
                fecha_ingreso_str = request.form["fecha_ingreso"]
                fecha_salida_str = request.form.get("fecha_salida")
                puesto_id = request.form["puesto_id"]
                tipo_nomina_id = request.form["tipo_nomina_id"]
                rol_id = request.form["rol_id"]
                estado_empleado = request.form.get("estado_empleado") == "on"
                estado_usuario = request.form.get("estado_usuario") == "on"

                # Lista para acumular errores de validación
                errores = []
                
                # Validaciones de duplicidad (excluyendo al empleado actual)
                if Empleado.query.filter(Empleado.cedula == cedula, Empleado.id_empleado != id).first():
                    errores.append("Ya existe un empleado con esa cédula en el sistema.")

                if Empleado.query.filter(Empleado.correo == correo, Empleado.id_empleado != id).first():
                    errores.append("Ya existe un empleado con ese correo electrónico en el sistema.")

                if Usuario.query.filter(Usuario.username == username, Usuario.id_usuario != empleado.Usuario_id_usuario).first():
                    errores.append("El nombre de usuario ya existe. Por favor, elige otro.")

                # Validaciones de formato
                email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                phone_regex = r"^[0-9]{8}$"
                
                if not re.match(email_regex, correo):
                    errores.append("El formato del correo electrónico no es válido.")

                if not re.match(phone_regex, telefono):
                    errores.append("El número de teléfono debe contener exactamente 8 dígitos.")
                
                try:
                    salario_base = float(salario_base_str)
                except ValueError:
                    errores.append("El salario debe ser un valor numérico.")

                # Si hay errores, mostrarlos y volver a renderizar el formulario
                if errores:
                    for error in errores:
                        flash(error, "danger")
                    return render_template(
                        "editar_empleado.html",
                        empleado=empleado,
                        roles=roles,
                        puestos=puestos,
                        tipos_nomina=tipos_nomina,
                        form_data=request.form # Pasa los datos del formulario para que no se pierdan
                    )

                # Actualizar datos del empleado
                empleado.nombre = nombre
                empleado.apellido_primero = apellido_primero
                empleado.apellido_segundo = apellido_segundo
                empleado.cedula = cedula
                empleado.correo = correo
                empleado.telefono = telefono
                empleado.salario_base = salario_base
                empleado.fecha_ingreso = datetime.strptime(fecha_ingreso_str, "%Y-%m-%d").date()
                empleado.estado_empleado = estado_empleado
                empleado.Puesto_id_puesto = puesto_id
                empleado.TipoNomina_id_tipo_nomina = tipo_nomina_id
                
                if fecha_salida_str:
                    empleado.fecha_salida = datetime.strptime(fecha_salida_str, "%Y-%m-%d").date()
                else:
                    empleado.fecha_salida = None

                # Actualizar datos de usuario asociados
                usuario = Usuario.query.get_or_404(empleado.Usuario_id_usuario)
                usuario.username = username
                usuario.Rol_id_rol = rol_id
                usuario.estado_usuario = estado_usuario

                db.session.commit()
                flash("Empleado actualizado exitosamente.", "success")
                return redirect(url_for("empleado.listar_empleado"))

            except Exception as e:
                db.session.rollback()
                logging.error(f"Error al actualizar el empleado: {str(e)}")
                flash(f"Ocurrió un error al actualizar el empleado: {str(e)}", "danger")
                return render_template(
                    "editar_empleado.html",
                    empleado=empleado,
                    roles=roles,
                    puestos=puestos,
                    tipos_nomina=tipos_nomina,
                )

        elif action == "restablecer_contrasena":
            try:
                usuario = empleado.usuario
                alphabet = string.ascii_letters + string.digits + string.punctuation
                temp_password = "".join(secrets.choice(alphabet) for i in range(8))

                usuario.password = generate_password_hash(temp_password)
                usuario.cambio_password_requerido = True
                db.session.commit()

                flash(
                    f'La contraseña para el usuario "{usuario.username}" ha sido restablecida. La nueva clave temporal es: <strong>{temp_password}</strong>',
                    "success",
                )
                return redirect(url_for("empleado.editar_empleado", id=empleado.id_empleado))

            except Exception as e:
                db.session.rollback()
                logging.error(f"Error al restablecer la contraseña: {str(e)}")
                flash(f"Ocurrió un error al restablecer la contraseña: {str(e)}", "danger")
                return redirect(url_for("empleado.editar_empleado", id=empleado.id_empleado))

    # Renderizar la plantilla en el método GET
    return render_template(
        "editar_empleado.html",
        empleado=empleado,
        roles=roles,
        puestos=puestos,
        tipos_nomina=tipos_nomina,
    )

# --------------------------------------------------------------------------------

@empleado_bp.route("/ver_perfil_empleado/<int:empleado_id>", methods=["GET"])
@login_required
def ver_perfil_empleado(empleado_id):
    try:
        usuario_actual = current_user
        
        # Obtener el empleado asociado al usuario actual
        empleado_actual = Empleado.query.filter_by(Usuario_id_usuario=usuario_actual.id_usuario).first()
        
        # Obtener el perfil del empleado que se desea ver (o 404 si no existe)
        empleado_perfil = Empleado.query.get_or_404(empleado_id)
        
        # Lógica de seguridad para verificar permisos (RNF-SE-009)
        # La corrección se hace aquí, usando "or []"
        es_admin = usuario_actual.rol.tipo_rol == 'administrador'
        
        # Si el usuario NO es un administrador Y el perfil solicitado no es el suyo, se deniega el acceso
        if not es_admin and empleado_perfil.id_empleado != empleado_actual.id_empleado:
            flash("Acceso denegado. No tiene los permisos necesarios para ver esta información.", "danger")
            return redirect(url_for("empleado.listar_empleado"))
            
        return render_template("ver_perfil_empleado.html", empleado=empleado_perfil)
    
    except Exception as e:
        logging.error(f"Error al cargar el perfil del empleado {empleado_id}: {str(e)}")
        
        flash("Error al cargar el perfil. Por favor, inténtelo de nuevo.", "danger")
        return redirect(url_for("empleado.listar_empleado"))

# ---------------------------------------------------------------------------------

@empleado_bp.route("/listar_empleado")
@permiso_requerido('listar_empleados')
@login_required
def listar_empleado():
    empleados = Empleado.query.all()
    return render_template("listar_empleado.html", empleados=empleados)

# -------------------------------------------------------------------------------

@empleado_bp.route("/eliminar_empleado/<int:id>", methods=["POST"])
@permiso_requerido('eliminar_empleado')
@login_required
def eliminar_empleado(id):
    empleado = Empleado.query.get_or_404(id)
    usuario = Usuario.query.get_or_404(empleado.Usuario_id_usuario)

    try:
        # 1. Eliminar los registros de asistencia del empleado
        RegistroAsistencia.query.filter_by(
            Empleado_id_empleado=empleado.id_empleado
        ).delete()

        # 2. Eliminar las nóminas del empleado
        Nomina.query.filter_by(Empleado_id_empleado=empleado.id_empleado).delete()

        # 3. Finalmente, eliminar el empleado y su usuario
        db.session.delete(empleado)
        db.session.delete(usuario)

        db.session.commit()
        flash("Empleado eliminado exitosamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ocurrió un error al eliminar el empleado: {str(e)}", "danger")

    return redirect(url_for("empleado.listar_empleado"))

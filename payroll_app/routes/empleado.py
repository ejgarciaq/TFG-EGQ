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


# Se crea un objeto Blueprint llamado 'empleado', que permite modularizar la aplicación Flask.
empleado_bp = Blueprint("empleado", __name__, template_folder="templates")


@empleado_bp.route("/crear_empleado", methods=["GET", "POST"])
def crear_empleado():
    roles = Rol.query.all()
    puestos = Puesto.query.all()
    # ❗❗❗ Obtener todos los tipos de nómina de la base de datos ❗❗❗
    tipos_nomina = TipoNomina.query.all()

    if request.method == "POST":
        # Obtener y validar todos los datos al inicio del bloque POST
        username = request.form["username"]
        password = request.form["password"]
        correo = request.form["correo"]
        telefono = request.form["telefono"]

        # Validaciones con expresiones regulares
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        phone_regex = r"^[0-9]{8}$"
        password_regex = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+-.,/])[A-Za-z\d!@#$%^&*()_+-.,/]{8,}$"

        if Usuario.query.filter_by(username=username).first():
            flash("El nombre de usuario ya existe. Por favor, elige otro.", "danger")
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
            # Crear el usuario y el empleado después de pasar todas las validaciones
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

            # ❗❗❗ Obtener el ID del tipo de nómina del formulario ❗❗❗
            tipo_nomina_id = request.form["tipo_nomina_id"]

            nuevo_empleado = Empleado(
                nombre=request.form["nombre"],
                apellido_primero=request.form["apellido_primero"],
                apellido_segundo=request.form.get("apellido_segundo"),
                cedula=request.form["cedula"],
                correo=correo,
                telefono=telefono,
                fecha_ingreso=fecha_ingreso,
                fecha_salida=None,
                salario_base=float(request.form["salario_base"]),
                estado_empleado=True,
                Puesto_id_puesto=request.form["puesto_id"],
                # ❗❗❗ Asignar el ID del tipo de nómina al nuevo empleado ❗❗❗
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
            # ❗❗❗ En caso de error, volver a pasar todos los datos al template ❗❗❗
            return render_template(
                "crear_empleado.html",
                puestos=puestos,
                roles=roles,
                tipos_nomina=tipos_nomina,
            )

    # ❗❗❗ Pasar el argumento 'tipos_nomina' al template en la petición GET ❗❗❗
    return render_template(
        "crear_empleado.html", puestos=puestos, roles=roles, tipos_nomina=tipos_nomina
    )


# ---------------------------------------------------------------------------------


@empleado_bp.route("/editar_empleado/<int:id>", methods=["GET", "POST"])
# @login_required
# @roles_required('Administrador')
def editar_empleado(id):
    empleado = Empleado.query.get_or_404(id)
    roles = Rol.query.all()
    puestos = Puesto.query.all()
    tipos_nomina = TipoNomina.query.all()

    if request.method == "POST":
        # ✅ Identifica la acción a realizar
        action = request.form.get("action")

        if action == "guardar_cambios":
            try:
                # Lógica de validación y actualización de datos del empleado
                required_fields = [
                    "username",
                    "nombre",
                    "apellido_primero",
                    "cedula",
                    "correo",
                    "telefono",
                    "salario_base",
                    "fecha_ingreso",
                    "puesto_id",
                    "tipo_nomina_id",
                    "rol_id",
                ]
                for field in required_fields:
                    if not request.form.get(field):
                        flash(
                            f'El campo "{field}" es obligatorio. Por favor, complétalo.',
                            "danger",
                        )
                        return redirect(url_for("empleado.editar_empleado", id=id))

                correo = request.form["correo"]
                telefono = request.form["telefono"]

                email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                phone_regex = r"^[0-9]{8}$"

                if not re.match(email_regex, correo):
                    flash("El formato del correo electrónico no es válido.", "danger")
                    return redirect(url_for("empleado.editar_empleado", id=id))

                if not re.match(phone_regex, telefono):
                    flash(
                        "El número de teléfono debe contener exactamente 8 dígitos.",
                        "danger",
                    )
                    return redirect(url_for("empleado.editar_empleado", id=id))

                # Actualizar datos del empleado
                empleado.nombre = request.form["nombre"]
                empleado.apellido_primero = request.form["apellido_primero"]
                empleado.apellido_segundo = request.form.get("apellido_segundo")
                empleado.cedula = request.form["cedula"]
                empleado.correo = correo
                empleado.telefono = telefono
                empleado.salario_base = float(request.form["salario_base"])

                empleado.fecha_ingreso = datetime.strptime(
                    request.form["fecha_ingreso"], "%Y-%m-%d"
                ).date()
                fecha_salida_str = request.form.get("fecha_salida")
                if fecha_salida_str:
                    empleado.fecha_salida = datetime.strptime(
                        fecha_salida_str, "%Y-%m-%d"
                    ).date()
                else:
                    empleado.fecha_salida = None

                empleado.estado_empleado = request.form.get("estado_empleado") == "on"
                empleado.Puesto_id_puesto = request.form["puesto_id"]
                empleado.TipoNomina_id_tipo_nomina = request.form["tipo_nomina_id"]

                # Actualizar datos de usuario asociados
                usuario = Usuario.query.get_or_404(empleado.Usuario_id_usuario)
                usuario.username = request.form["username"]
                usuario.Rol_id_rol = request.form["rol_id"]
                usuario.estado_usuario = request.form.get("estado_usuario") == "on"

                db.session.commit()
                flash("Empleado actualizado exitosamente.", "success")
                return redirect(url_for("empleado.listar_empleado"))

            except Exception as e:
                db.session.rollback()
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
                # ✅ Lógica para restablecer la contraseña
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
                return redirect(
                    url_for("empleado.editar_empleado", id=empleado.id_empleado)
                )

            except Exception as e:
                db.session.rollback()
                flash(
                    f"Ocurrió un error al restablecer la contraseña: {str(e)}", "danger"
                )
                return redirect(
                    url_for("empleado.editar_empleado", id=empleado.id_empleado)
                )

    # Renderizar la plantilla en el método GET
    return render_template(
        "editar_empleado.html",
        empleado=empleado,
        roles=roles,
        puestos=puestos,
        tipos_nomina=tipos_nomina,
    )


# ---------------------------------------------------------------------------------


@empleado_bp.route("/listar_empleado")
def listar_empleado():
    empleados = Empleado.query.all()
    return render_template("listar_empleado.html", empleados=empleados)


@empleado_bp.route("/eliminar_empleado/<int:id>", methods=["POST"])
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

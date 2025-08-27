from payroll_app import create_app, db
from payroll_app import models
from flask import render_template


# Llama a la funcion create_app para crear la instancia de la aplicación Flask
app = create_app()

# validar las tablas y la base de datos
with app.app_context():
    db.create_all()
    print("Base de datos y tablas creadas exitosamente.")

# Ruta para la página de inicio
@app.route('/')
def index():
    return render_template('index.html')

# Verifica si el script se está ejecutando directamente
if __name__ == '__main__':
    # Ejecuta la aplicación en modo de depuración
    app.run(debug=True)
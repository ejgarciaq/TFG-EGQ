from flask import render_template
from payroll_app import create_app


# Llama a la funcion create_app para crear la instancia de la aplicación Flask
app = create_app()

# Ruta para la página de inicio
@app.route('/')
def index():
    return render_template('index.html')

# Verifica si el script se está ejecutando directamente
if __name__ == '__main__':
    # Ejecuta la aplicación en modo de depuración
    app.run(debug=True)
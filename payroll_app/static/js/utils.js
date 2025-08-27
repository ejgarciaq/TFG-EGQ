/* función para mostrar o ocultar la contraseña */
function togglePassword() {
    var passwordField = document.getElementById("password");
    if (passwordField.type === "password") {
        passwordField.type = "text"; // Mostrar contraseña
    } else {
        passwordField.type = "password"; // Ocultar contraseña
    }
}

// Este script se encargará de ocultar las alertas automáticamente.
document.addEventListener('DOMContentLoaded', (event) => {
    // Selecciona todos los elementos con la clase 'alert'
    const alerts = document.querySelectorAll('.alert');

    // Itera sobre cada alerta y programa su cierre
    alerts.forEach(alert => {
        setTimeout(() => {
            // Cierra la alerta después de 5000 milisegundos (5 segundos)
            alert.style.display = 'none';
        }, 7000);
    });
});


/*reloj y la fecha  */
document.addEventListener('DOMContentLoaded', () => {
    const reloj = document.getElementById('reloj');
    const fechaActual = document.getElementById('fecha_actual');
    const marcarBtn = document.getElementById('marcar_btn');
    const formAsistencia = document.getElementById('form_asistencia');

    // Función para actualizar el reloj y la fecha
    function actualizarReloj() {
        const ahora = new Date();
        const hora = ahora.toLocaleTimeString('es-CR', { hour12: false });
        const fecha = ahora.toLocaleDateString('es-CR', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });

        reloj.textContent = hora;
        fechaActual.textContent = fecha;
    }

    // Actualiza el reloj cada segundo
    setInterval(actualizarReloj, 1000);
    actualizarReloj(); // Llama a la función una vez al cargar la página

    // Lógica del botón de marcar
    marcarBtn.addEventListener('click', async () => {
        // La ruta de Flask manejará toda la lógica de validación y guardado
        // Simplemente enviamos el formulario cuando el usuario hace clic.
        // El servidor recibirá la hora real del servidor (recomendado) o 
        // la hora actual del cliente, que se puede enviar en un campo oculto si se desea.
        // En este caso, la ruta en Python usa datetime.utcnow() para mayor seguridad.
        formAsistencia.submit();
    });
});
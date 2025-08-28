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


// Función para actualizar el reloj y la fecha
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

        // Esta es la línea clave: Actualiza TODO el contenido del div
		reloj.textContent = hora;
        fechaActual.textContent = fecha;
    }

	setInterval(actualizarReloj, 1000);
	actualizarReloj();

	marcarBtn.addEventListener('click', async () => {
	formAsistencia.submit();
  });
});
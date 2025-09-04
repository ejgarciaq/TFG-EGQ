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
    const horaClienteInput = document.getElementById('hora_cliente_input');
    const fechaClienteInput = document.getElementById('fecha_cliente_input');

    // Función para actualizar el reloj y la fecha
    function actualizarReloj() {
        const ahora = new Date();
        
        // Formato para la hora (ej: 14:30:05)
        const hora = ahora.toLocaleTimeString('es-CR', { hour12: false });
        
        // Formato para la fecha (ej: jueves, 29 de agosto de 2025)
        const fecha = ahora.toLocaleDateString('es-CR', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });

        // Actualiza el texto visible del reloj y la fecha
        reloj.textContent = hora;
        fechaActual.textContent = fecha;

        // ❗ Actualiza los valores de los campos ocultos
        horaClienteInput.value = hora; // Usa el mismo formato HH:MM:SS
        fechaClienteInput.value = ahora.toISOString().split('T')[0]; // Formato YYYY-MM-DD
    }

    // Actualiza el reloj cada segundo
    setInterval(actualizarReloj, 1000);
    actualizarReloj(); // Llama a la función una vez al inicio

    marcarBtn.addEventListener('click', async () => {
        // La hora y fecha ya están actualizadas en los campos ocultos por el intervalo
        formAsistencia.submit();
    });
});
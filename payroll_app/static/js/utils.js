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
        }, 2000);
    });
});
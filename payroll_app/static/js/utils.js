/* función para mostrar o ocultar la contraseña */
function togglePassword() {
    var passwordField = document.getElementById("password");
    if (passwordField.type === "password") {
        passwordField.type = "text"; // Mostrar contraseña
    } else {
        passwordField.type = "password"; // Ocultar contraseña
    }
}

/* función para mostrar o ocultar la contraseña */
function togglePassword() {
  var passwordField = document.getElementById("password");
  if (passwordField.type === "password") {
    passwordField.type = "text"; // Mostrar contraseña
  } else {
    passwordField.type = "password"; // Ocultar contraseña
  }
}

/* Oculta las alertas flash autmáticamente a un tiempo programado*/
document.addEventListener("DOMContentLoaded", () => {
    // Selecciona el contenedor de todas las alertas
    const flashesContainer = document.querySelector(".flashes");

    if (flashesContainer) { // Solo si el contenedor de flashes existe
        const alerts = flashesContainer.querySelectorAll(".alert");
        let activeAlerts = alerts.length; // Contador de alertas activas

        alerts.forEach((alertElement) => {
            // Inicializa el componente Alert de Bootstrap
            const bsAlert = new bootstrap.Alert(alertElement);

            // Escucha el evento 'closed.bs.alert' que se dispara cuando la alerta ha terminado de desaparecer
            alertElement.addEventListener('closed.bs.alert', () => {
                activeAlerts--; // Decrementa el contador de alertas activas
                // Si ya no quedan alertas activas en el contenedor, ocultamos el contenedor
                if (activeAlerts === 0) {
                    flashesContainer.style.display = 'none';
                }
            });
            // Programa el cierre automático de cada alerta
            setTimeout(() => {
                bsAlert.close(); // Usa .close() para activar la transición y el evento 'closed.bs.alert'
            }, 7000); // Cierra después de 7 segundos
        });
    }
});

/* Lógica para el reloj y la gestión del botón único de asistencia */
document.addEventListener("DOMContentLoaded", () => {
    const reloj = document.getElementById("reloj");
    const fechaActual = document.getElementById("fecha_actual");
    const formAsistencia = document.getElementById("form_asistencia");

    function actualizarReloj() {
        const ahora = new Date();
        const hora = ahora.toLocaleTimeString("es-CR", { hour12: false });
        const fecha = ahora.toLocaleDateString("es-CR", {
            weekday: "long", year: "numeric", month: "long", day: "numeric",
        });

        if (reloj) reloj.textContent = hora;
        if (fechaActual) fechaActual.textContent = fecha;
    }

    setInterval(actualizarReloj, 1000);
    actualizarReloj();

    // --- LÓGICA PARA GESTIONAR EL BOTÓN ÚNICO ---
    const btnText = document.getElementById('btn_text');
    const btnIcon = document.getElementById('btn_icon');
    const marcarBtn = document.getElementById("marcar_btn");
    // Obtenemos el estado actual desde el atributo data del contenedor principal
    const containerElement = document.querySelector('.container');
    const estadoActual = containerElement && containerElement.dataset.estadoActual
                         ? containerElement.dataset.estadoActual.trim() // Aseguramos que no haya espacios extra
                         : "entrada"; // Valor por defecto si no se encuentra el atributo
    let textoBoton = "";
    let iconoBoton = "";
    let valorAccion = "";
    let claseBoton = "btn-primary";

    switch (estadoActual) {
        case 'entrada':
            console.log("DEBUG (JS): Switch cayó en 'entrada'");
            textoBoton = "Marcar Entrada";
            iconoBoton = "fas fa-sign-in-alt";
            valorAccion = "entrada";
            claseBoton = "btn-success";
            break;
        case 'salida_almuerzo':
            console.log("DEBUG (JS): Switch cayó en 'salida_almuerzo'");
            textoBoton = "Salida a Almuerzo";
            iconoBoton = "fas fa-utensils";
            valorAccion = "salida_almuerzo";
            claseBoton = "btn-warning";
            break;
        case 'regreso_almuerzo':
            console.log("DEBUG (JS): Switch cayó en 'regreso_almuerzo'");
            textoBoton = "Regreso del Almuerzo";
            iconoBoton = "fas fa-mug-hot";
            valorAccion = "regreso_almuerzo";
            claseBoton = "btn-info";
            break;
        case 'salida_final':
            console.log("DEBUG (JS): Switch cayó en 'salida_final'");
            textoBoton = "Finalizar Jornada";
            iconoBoton = "fas fa-sign-out-alt";
            valorAccion = "salida_final";
            claseBoton = "btn-danger";
            break;
        case 'jornada_completa_hoy':
            console.log("DEBUG (JS): Switch cayó en 'jornada_completa_hoy'");
            textoBoton = "Jornada Finalizada Hoy";
            iconoBoton = "fas fa-check-circle";
            valorAccion = "jornada_finalizada"; // Esto es lo que se enviaría si se pulsara, aunque el botón debería estar deshabilitado
            claseBoton = "btn-secondary disabled";
            if (marcarBtn) marcarBtn.disabled = true; // Deshabilita el botón
            break;
        default:
            textoBoton = "Error de Estado"; // Texto por defecto si no se reconoce el estado
            iconoBoton = "fas fa-exclamation-triangle";
            valorAccion = "error"; // Valor por defecto para enviar si el estado es desconocido
            claseBoton = "btn-secondary";
            if (marcarBtn) marcarBtn.disabled = true; // Deshabilita el botón
            break;
    }

    // Estas líneas aplican el estado calculado al botón.
    // Añadimos comprobaciones `if (elemento)` por seguridad.
    if (btnText) btnText.textContent = textoBoton;
    if (btnIcon) btnIcon.className = iconoBoton;
    if (marcarBtn) {
        marcarBtn.value = valorAccion; // Esto es CLAVE: asigna el valor que se enviará al backend
        marcarBtn.classList.remove('btn-primary', 'btn-success', 'btn-warning', 'btn-info', 'btn-danger', 'btn-secondary');
        marcarBtn.classList.add(claseBoton);
    }
});

/* Lógica para mostrar/ocultar campos según el tipo de acción y calcular días laborales */
document.addEventListener('DOMContentLoaded', function() {
    // Definimos todos los elementos del DOM.
    const tipoApSelect = document.getElementById('tipo_ap_id');
    const empleadoSelect = $('#empleado_id');
    const vacationFields = document.getElementById('vacation_fields');
    const incapacityLeaveFields = document.getElementById('incapacity_leave_fields');
    const saldoVacacionesInput = document.getElementById('saldo_vacaciones_input');
    const cantidadDiaVacacionesInput = document.getElementById('cantidad_dia_vac');
    const cantidadDiaIncapacidadInput = document.getElementById('cantidad_dia_inc');
    const fechaInicioVacacionesInput = document.getElementById('fecha_inicio');
    const fechaFinVacacionesInput = document.getElementById('fecha_fin');
    const fechaInicioIncapacidadInput = document.getElementById('fecha_inicio_inc');
    const fechaFinIncapacidadInput = document.getElementById('fecha_fin_inc');
    
    // Función para actualizar el saldo de vacaciones
    function actualizarSaldoVacaciones() {
        const selectedEmpleadoOption = empleadoSelect.find(':selected');
        const saldoVacaciones = selectedEmpleadoOption.data('vacaciones');
        
        if (saldoVacaciones !== null && saldoVacaciones !== undefined) {
            saldoVacacionesInput.value = parseInt(saldoVacaciones);
        } else {
            saldoVacacionesInput.value = '';
        }
    }

    // Función principal para mostrar/ocultar los campos según el tipo de acción
    function actualizarCampos() {
        const selectedOption = tipoApSelect.options[tipoApSelect.selectedIndex];
        const nombreTipo = selectedOption.getAttribute('data-nombre-tipo');

        // Ocultar ambos contenedores primero
        vacationFields.style.display = 'none';
        incapacityLeaveFields.style.display = 'none';
        
        // Mostrar el contenedor correcto basado en el nombre del tipo de acción
        if (nombreTipo === 'Vacaciones') {
            vacationFields.style.display = 'block';
            actualizarSaldoVacaciones();
        } else if (nombreTipo === 'Incapacidad' || nombreTipo === 'Permiso c/ Goce de Salario') {
            incapacityLeaveFields.style.display = 'block';
        }
    }

    // Función auxiliar para verificar si una fecha es feriada
    function isHoliday(date, diasFestivos) {
        const dateString = date.toISOString().slice(0, 10);
        return diasFestivos.includes(dateString);
    }
    
    // Función para calcular días laborales para Vacaciones
    function calcularDiasLaboralesVacaciones() {
        const fechaInicioStr = fechaInicioVacacionesInput.value;
        const fechaFinStr = fechaFinVacacionesInput.value;
        if (fechaInicioStr && fechaFinStr) {
            const diasFeriados = JSON.parse(vacationFields.getAttribute('data-dias-festivos'));
            let fechaInicio = new Date(fechaInicioStr + 'T00:00:00');
            let fechaFin = new Date(fechaFinStr + 'T00:00:00');
            let diasLaborales = 0;
            let currentDate = fechaInicio;

            while (currentDate <= fechaFin) {
                const diaSemana = currentDate.getDay(); // 0 = Domingo, 1 = Lunes
                if (diaSemana >= 1 && diaSemana <= 6 && !isHoliday(currentDate, diasFeriados)) {
                    diasLaborales++;
                }
                currentDate.setDate(currentDate.getDate() + 1);
            }
            cantidadDiaVacacionesInput.value = diasLaborales;
        }
    }

    // Función para calcular días laborales para Incapacidad y Permiso
    function calcularDiasLaboralesIncapacidad() {
        const fechaInicioStr = fechaInicioIncapacidadInput.value;
        const fechaFinStr = fechaFinIncapacidadInput.value;
        if (fechaInicioStr && fechaFinStr) {
            const diasFeriados = JSON.parse(incapacityLeaveFields.getAttribute('data-dias-festivos'));
            let fechaInicio = new Date(fechaInicioStr + 'T00:00:00');
            let fechaFin = new Date(fechaFinStr + 'T00:00:00');
            let diasLaborales = 0;
            let currentDate = fechaInicio;

            while (currentDate <= fechaFin) {
                const diaSemana = currentDate.getDay();
                if (diaSemana >= 1 && diaSemana <= 5 && !isHoliday(currentDate, diasFeriados)) {
                    diasLaborales++;
                }
                currentDate.setDate(currentDate.getDate() + 1);
            }
            cantidadDiaIncapacidadInput.value = diasLaborales;
        }
    }
    
    // 3. Establecer los EventListeners con la sintaxis correcta para Select2
    // Usamos 'change' en la selección de empleado para actualizar las vacaciones disponibles
    empleadoSelect.on('change', actualizarSaldoVacaciones); 
    // Usamos 'change' en el tipo de acción para mostrar/ocultar los campos
    $(tipoApSelect).on('change', actualizarCampos);
    
    // Eventos para el cálculo de días de vacaciones
    fechaInicioVacacionesInput.addEventListener('change', calcularDiasLaboralesVacaciones);
    fechaFinVacacionesInput.addEventListener('change', calcularDiasLaboralesVacaciones);

    // Eventos para el cálculo de días de incapacidad
    fechaInicioIncapacidadInput.addEventListener('change', calcularDiasLaboralesIncapacidad);
    fechaFinIncapacidadInput.addEventListener('change', calcularDiasLaboralesIncapacidad);

    // 4. Inicializar el estado del formulario al cargar la página
    actualizarCampos();
});

/* Lógica para validar los requisitos de la contraseña y controlar el envío del formulario */
document.addEventListener('DOMContentLoaded', function() {
    // Obtener elementos clave del DOM, verificando el campo principal de entrada
    const passwordInput = document.getElementById('nueva_contrasena');
    
    // Si el campo de contraseña NO existe, salimos inmediatamente
    if (!passwordInput) {
        // console.log("DEBUG: Campo 'nueva_contrasena' no encontrado. Saltando validación de contraseña.");
        return; 
    }
    
    // A partir de aquí, el código solo se ejecuta si estamos en la página correcta
    
    const form = document.querySelector('form');
    const confirmInput = document.getElementById('confirmar_contrasena');
    const submitButton = form.querySelector('button[type="submit"]');

    // Requisitos de complejidad
    const lengthReq = document.getElementById('length-req');
    const uppercaseReq = document.getElementById('uppercase-req');
    const lowercaseReq = document.getElementById('lowercase-req');
    const numberReq = document.getElementById('number-req');
    const symbolReq = document.getElementById('symbol-req');
    const confirmReq = document.getElementById('confirm-req');

    // Deshabilitar el botón de envío por defecto
    submitButton.disabled = true;

    // Escuchar eventos de teclado en ambos campos
    passwordInput.addEventListener('keyup', validatePassword);
    confirmInput.addEventListener('keyup', validatePassword);
    
    // ... (El resto de la función validatePassword() y updateRequirement() queda igual)
    function validatePassword() {
        const password = passwordInput.value;
        const confirmPassword = confirmInput.value;

        // ... (Tu lógica de validación de complejidad e isMatchValid) ...
        const isLengthValid = password.length >= 8;
        const isUppercaseValid = /[A-Z]/.test(password);
        const isLowercaseValid = /[a-z]/.test(password);
        const isNumberValid = /[0-9]/.test(password);
        const isSymbolValid = /[@$!%*?&]/.test(password);
        const isMatchValid = password === confirmPassword && confirmPassword.length > 0;

        // Actualizar la interfaz (se asume que los elementos existen por la verificación inicial)
        updateRequirement(lengthReq, isLengthValid);
        updateRequirement(uppercaseReq, isUppercaseValid);
        updateRequirement(lowercaseReq, isLowercaseValid);
        updateRequirement(numberReq, isNumberValid);
        updateRequirement(symbolReq, isSymbolValid);
        updateRequirement(confirmReq, isMatchValid);

        // Comprobar estado final para el botón
        const allComplexValid = isLengthValid && isUppercaseValid && isLowercaseValid && isNumberValid && isSymbolValid;
        submitButton.disabled = !(allComplexValid && isMatchValid);
    }

    function updateRequirement(element, isValid) {
        const icon = element.querySelector('i');
        if (icon) {
            if (isValid) {
                element.classList.remove('text-danger');
                element.classList.add('text-success');
                icon.classList.remove('fa-times-circle');
                icon.classList.add('fa-check-circle');
            } else {
                element.classList.remove('text-success');
                element.classList.add('text-danger');
                icon.classList.remove('fa-check-circle');
                icon.classList.add('fa-times-circle');
            }
        }
    }
    
    validatePassword(); 
});

/* Solo se ejecuta si estamos en la página correcta (existe el campo 'password' y el botón 'generatePasswordBtn') */
const passwordInput = document.getElementById('password');
const generatePasswordBtn = document.getElementById('generatePasswordBtn');

if (passwordInput && generatePasswordBtn) {

    function generatePassword() {
        const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*";
        
        // Función interna para validar la complejidad
        const isValid = (password) => {
            const hasLength = password.length >= 8;
            const hasUppercase = /[A-Z]/.test(password);
            const hasLowercase = /[a-z]/.test(password);
            const hasNumber = /[0-9]/.test(password);
            const hasSymbol = /[@$!%*?&]/.test(password);
            return hasLength && hasUppercase && hasLowercase && hasNumber && hasSymbol;
        };

        let password = "";
        do {
            password = ""; // Reinicia la contraseña si no es válida
            for (let i = 0; i < 12; i++) {
                password += chars.charAt(Math.floor(Math.random() * chars.length));
            }
        } while (!isValid(password)); // Repite hasta que la contraseña sea válida
        
        return password;
    }

    generatePasswordBtn.addEventListener('click', () => {
        passwordInput.value = generatePassword();
    });
}

/* jQuery y clase CSS Select2 están cargados antes de este script */
$(document).ready(function() {
    // Inicialización de Select2 en el campo de empleados
    $('.select2').select2({
        placeholder: "Buscar y seleccionaro...",
        allowClear: true,
        theme: "bootstrap-5"
    });
});

/* Seleccionar o deseleccionar todos los checkboxes */
document.getElementById('seleccionar_todo').addEventListener('change', function() {
    var checkboxes = document.querySelectorAll('input[name="registros_seleccionados"]');
        for (var i = 0; i < checkboxes.length; i++) {
            checkboxes[i].checked = this.checked;
        }
});




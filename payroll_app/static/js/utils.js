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


document.addEventListener('DOMContentLoaded', function() {
    const fechaInicioInput = document.getElementById('fecha_inicio');
    const fechaFinInput = document.getElementById('fecha_fin');
    const cantidadDiasInput = document.getElementById('cantidad_dia');
    
    // Los IDs de los tipos de acción
    const VACACIONES_ID = 6;
    const INCAPACIDAD_ID = 5;

    // Lee los datos del atributo del div
    const vacationIncapacityFields = document.getElementById('vacation_incapacity_fields');
    const diasFestivos = JSON.parse(vacationIncapacityFields.dataset.diasFestivos);

    function isHoliday(date) {
        const dateString = date.toISOString().slice(0, 10);
        return diasFestivos.includes(dateString);
    }

    function calculateBusinessDays() {
        // Asegura una zona horaria consistente para la fecha de inicio y fin
        const fechaInicio = new Date(fechaInicioInput.value + 'T00:00:00');
        const fechaFin = new Date(fechaFinInput.value + 'T00:00:00');
            
        if (!fechaInicioInput.value || !fechaFinInput.value) {
            cantidadDiasInput.value = '';
            return;
        }

        let diasLaborables = 0;
        for (let d = new Date(fechaInicioInput.value + 'T00:00:00'); d <= fechaFin; d.setDate(d.getDate() + 1)) {
            const diaDeLaSemana = d.getDay(); // 0 = Domingo, 6 = Sábado
            if (diaDeLaSemana !== 0 && !isHoliday(d)) { // <-- ¡para agregar sabados! if (diaDeLaSemana !== 0 && diaDeLaSemana !== 6 && !isHoliday(d))
                diasLaborables++;
            }
        }
        cantidadDiasInput.value = diasLaborables;
    }

    // Agrega un listener para cuando el usuario cambie las fechas
    fechaInicioInput.addEventListener('change', calculateBusinessDays);
    fechaFinInput.addEventListener('change', calculateBusinessDays);

    // Lógica para mostrar/ocultar los campos según el tipo de acción
    const tipoApSelect = document.getElementById('tipo_ap_id');

    function toggleFieldsAndCalculate() {
        const selectedId = parseInt(tipoApSelect.value);
        if (selectedId === VACACIONES_ID || selectedId === INCAPACIDAD_ID) {
            vacationIncapacityFields.style.display = 'block';
            calculateBusinessDays();
        } else {
            vacationIncapacityFields.style.display = 'none';
            cantidadDiasInput.value = '';
        }
    }
        
    tipoApSelect.addEventListener('change', toggleFieldsAndCalculate);
    toggleFieldsAndCalculate();
});
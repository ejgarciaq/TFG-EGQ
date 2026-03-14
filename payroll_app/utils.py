import json
from datetime import timedelta
from payroll_app.models import Configuracion, db

def cargar_configuracion():
    """
    Carga todos los parámetros de la BD y convierte los valores de string 
    al tipo de dato Python (float, int, timedelta).
    """ 
    config_dict = {}
    parametros = Configuracion.query.all()

    for param in parametros:
        valor_convertido = None
        # Lógica de Conversión
        if param.tipo_dato == 'float':
            valor_convertido = float(param.valor_parametro)
        elif param.tipo_dato == 'int':
            valor_convertido = int(param.valor_parametro)
        # Conversión a timedelta (Horas)
        elif param.tipo_dato == 'timedelta_h':
            valor_convertido = timedelta(hours=float(param.valor_parametro))
        elif param.tipo_dato == 'timedelta_m':
            valor_convertido = timedelta(minutos=float(param.valor_parametro))

        elif param.tipo_dato == 'json':
            try:
                valor_convertido = json.loads(param.valor_parametro)
            except json.JSONDecodeError:
                continue
        
        else:
            valor_convertido = param.valor_parametro
        
        config_dict[param.nombre_parametro] = valor_convertido

    return config_dict





        
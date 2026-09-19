# -*- coding: utf-8 -*-
"""
services/logs.py — auditoría de acciones administrativas (tabla log_auditoria).

Ver punto 2.3 del documento de cambios v1.2.

`log_event` NUNCA lanza una excepción hacia arriba: si el registro de log
falla (por ejemplo, la tabla no existe todavía en una BD a medio migrar),
se captura el error y se informa vía `flash_fn` (o `print` si no se pasa),
pero la operación principal (cerrar un mes, finalizar una obra...) no debe
romperse por ello.
"""
import json
from datetime import datetime


def log_event(db, tipo_evento, entidad, entidad_id, obra_id, detalle_dict, flash_fn=None):
    """
    Inserta un evento de auditoría dentro de la transacción abierta en `db`.

    tipo_evento: 'CIERRE_MENSUAL', 'REABRIR_MENSUAL', 'CERRAR_OBRA',
                 'REACTIVAR_OBRA', 'DOC_ARCHIVAR_PARTIDA', ...
    entidad:     'mensual', 'obra', 'partida', ...
    entidad_id:  id_mensual / id_obra / id_partida, según la entidad.
    obra_id:     siempre relleno para eventos de obra.
    detalle_dict: dict con contexto adicional; se le añade siempre obra_id.
    """
    try:
        detalle = dict(detalle_dict or {})
        detalle['obra_id'] = obra_id
        payload = json.dumps(detalle, ensure_ascii=False)
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute(
            "INSERT INTO log_auditoria(fecha,tipo_evento,entidad,entidad_id,obra_id,detalle) "
            "VALUES(?,?,?,?,?,?)",
            [fecha, tipo_evento, entidad, entidad_id, obra_id, payload])
    except Exception as e:
        msg = f"No se pudo registrar el evento de auditoría '{tipo_evento}': {e}"
        if flash_fn:
            try:
                flash_fn(msg, 'warning')
            except Exception:
                print(f'[log_auditoria] {msg}')
        else:
            print(f'[log_auditoria] {msg}')

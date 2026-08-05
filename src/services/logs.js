'use strict';
/**
 * services/logs.js — auditoría de acciones administrativas (tabla log_auditoria).
 *
 * Equivalente a services/logs.py. `logEvent` NUNCA lanza una excepción hacia
 * arriba: si el registro de log falla (por ejemplo, la tabla no existe
 * todavía en una BD a medio migrar), se captura el error y se informa vía
 * `flashFn` (o `console.warn` si no se pasa), pero la operación principal
 * (cerrar un mes, finalizar una obra...) no debe romperse por ello.
 */

/**
 * Inserta un evento de auditoría dentro de la transacción abierta en `db`.
 *
 * tipoEvento: 'CIERRE_MENSUAL', 'REABRIR_MENSUAL', 'CERRAR_OBRA',
 *             'REACTIVAR_OBRA', 'DOC_ARCHIVAR_PARTIDA', ...
 * entidad:    'mensual', 'obra', 'partida', ...
 * entidadId:  id_mensual / id_obra / id_partida, según la entidad.
 * obraId:     siempre relleno para eventos de obra.
 * detalleObj: objeto con contexto adicional; se le añade siempre obra_id.
 */
function logEvent(db, tipoEvento, entidad, entidadId, obraId, detalleObj, flashFn = null) {
  try {
    const detalle = { ...(detalleObj || {}), obra_id: obraId };
    const payload = JSON.stringify(detalle);
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const fecha =
      `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
      `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    db.prepare(
      `INSERT INTO log_auditoria(fecha,tipo_evento,entidad,entidad_id,obra_id,detalle)
       VALUES(?,?,?,?,?,?)`
    ).run(fecha, tipoEvento, entidad, entidadId, obraId, payload);
  } catch (e) {
    const msg = `No se pudo registrar el evento de auditoría '${tipoEvento}': ${e.message}`;
    if (flashFn) {
      try {
        flashFn(msg, 'warning');
      } catch (e2) {
        console.warn(`[log_auditoria] ${msg}`);
      }
    } else {
      console.warn(`[log_auditoria] ${msg}`);
    }
  }
}

module.exports = { logEvent };

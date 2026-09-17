'use strict';
/**
 * services/carryover.js — arrastre temporal inteligente.
 *
 * Calcula la fecha de origen del arrastre saltando fines de semana (y,
 * opcionalmente, festivos). El usuario final no necesita indicar manualmente
 * desde qué día quiere copiar: la lógica salta automáticamente sábados,
 * domingos y festivos configurados.
 *
 * Ejemplo: si hoy es lunes 16 de septiembre, el arrastre busca el viernes
 * 13 (no el domingo 15), porque en obras no se trabaja en fin de semana
 * por defecto.
 *
 * Para festivos especiales (días autonómicos, puentes...), se puede pasar
 * un array de cadenas 'YYYY-MM-DD' en `holidaysList`.
 */

/**
 * Devuelve la fecha del último día laborable anterior a `fechaStr`.
 *
 * fechaStr:     string 'YYYY-MM-DD'
 * maxRetroceso: nº máximo de días a retroceder (evita loops infinitos)
 * holidaysList: array de strings 'YYYY-MM-DD' a saltar (opcional)
 * skipWeekends: si true (por defecto), salta sábados y domingos
 *
 * Devuelve string 'YYYY-MM-DD' del día laboral más reciente, o null si no
 * se encuentra uno dentro de `maxRetroceso` días.
 */
function ultimoDiaLaboral(fechaStr, { maxRetroceso = 30, holidaysList = [], skipWeekends = true } = {}) {
  const holidaysSet = new Set(holidaysList);
  const parts = fechaStr.split('-').map(Number);
  const dt = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));

  for (let i = 0; i < maxRetroceso; i++) {
    dt.setUTCDate(dt.getUTCDate() - 1);
    const dow = dt.getUTCDay(); // 0=dom, 6=sab
    if (skipWeekends && (dow === 0 || dow === 6)) continue;
    const iso = toISO(dt);
    if (holidaysSet.has(iso)) continue;
    return iso;
  }
  return null;
}

/**
 * Busca en la BD el diario de obra `idObra` cuya fecha sea la más
 * reciente respecto a `fechaStr`, pero filtrando solo días laborables.
 *
 * Si existe un diario exactamente en `ultimoDiaLaboral()`, lo devuelve.
 * Si no, cae al plan B: el diario más reciente con fecha < fechaStr
 * (el comportamiento clásico, que cubre el caso de una semana con
 * varios días sin parte).
 *
 * db:           conexión better-sqlite3
 * idObra:       id de obra
 * fechaStr:     'YYYY-MM-DD' del día actual
 * opts:         mismas opciones que ultimoDiaLaboral
 *
 * Devuelve el row `diario` encontrado, o null.
 */
function buscarDiarioParaArrastre(db, idObra, fechaStr, opts = {}) {
  const diaLab = ultimoDiaLaboral(fechaStr, opts);
  if (diaLab) {
    const exact = db
      .prepare('SELECT * FROM diario WHERE id_obra=? AND fecha=?')
      .get(idObra, diaLab);
    if (exact) return exact;
  }
  // Plan B: el diario más reciente anterior a la fecha (comportamiento clásico)
  return db
    .prepare('SELECT * FROM diario WHERE id_obra=? AND fecha<? ORDER BY fecha DESC LIMIT 1')
    .get(idObra, fechaStr) || null;
}

/** Formatea un Date UTC como 'YYYY-MM-DD'. */
function toISO(dt) {
  const y = dt.getUTCFullYear();
  const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const d = String(dt.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

module.exports = { ultimoDiaLaboral, buscarDiarioParaArrastre };

'use strict';
/**
 * services/backup.js — copias de seguridad automatizadas con política de
 * retención y verificación de integridad.
 *
 * Funciona tanto desde el CLI (`npm run backup`) como importado
 * programáticamente para backups automáticos durante el arranque o a
 * intervalos configurados.
 *
 * Usa la API de backup de better-sqlite3, que internamente emplea la
 * Online Backup API de SQLite (sqlite3_backup_*) para copias en caliente
 * sin bloquear escritores concurrentes.
 */
const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');
const config = require('../config');
const { norm } = require('./fechas');

/**
 * Crea un backup de la BD activa.
 *
 * @param {Database} db           Conexión better-sqlite3 abierta.
 * @param {string}   [contexto]   Etiqueta para el nombre del fichero
 *                                (p.ej. código/nombre de obra). Por
 *                                defecto 'AUTO'.
 * @returns {Promise<string>}     Ruta absoluta del fichero de backup creado.
 */
async function crearBackup(db, contexto = 'AUTO') {
  fs.mkdirSync(config.BACKUP_DIR, { recursive: true });
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_` +
    `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const nombre = `backup_${stamp}_${norm(contexto) || 'AUTO'}.db`;
  const ruta = path.join(config.BACKUP_DIR, nombre);
  await db.backup(ruta);
  return ruta;
}

/**
 * Verifica la integridad de un fichero de backup abriéndolo y ejecutando
 * `PRAGMA integrity_check`.
 *
 * @param {string} rutaBackup  Ruta absoluta al fichero .db
 * @returns {{ ok: boolean, detail: string }}
 */
function verificarIntegridad(rutaBackup) {
  let testDb;
  try {
    testDb = new Database(rutaBackup, { readonly: true });
    const result = testDb.pragma('integrity_check');
    // integrity_check devuelve un array de objetos; si todo va bien,
    // el primer (y único) resultado es { integrity_check: 'ok' }.
    const allOk =
      result.length === 1 &&
      String(result[0].integrity_check).toLowerCase() === 'ok';
    return {
      ok: allOk,
      detail: allOk ? 'ok' : result.map((r) => r.integrity_check).join('; '),
    };
  } catch (e) {
    return { ok: false, detail: `Error al abrir: ${e.message}` };
  } finally {
    if (testDb) {
      try { testDb.close(); } catch (_) { /* ignore */ }
    }
  }
}

/**
 * Aplica la política de retención: borra los backups más antiguos si
 * se supera el límite de ficheros o de días.
 *
 * @param {object}  opts
 * @param {number}  [opts.maxFiles=30]  Nº máximo de ficheros a conservar.
 * @param {number}  [opts.maxDays=90]   Días máximos de antigüedad.
 * @returns {string[]}  Nombres de los ficheros eliminados.
 */
function aplicarRetencion({ maxFiles = 30, maxDays = 90 } = {}) {
  fs.mkdirSync(config.BACKUP_DIR, { recursive: true });
  const todos = fs
    .readdirSync(config.BACKUP_DIR)
    .filter((f) => f.startsWith('backup_') && f.endsWith('.db'))
    .sort(); // orden cronológico ascendente por la marca de tiempo en el nombre

  const ahora = Date.now();
  const maxMs = maxDays * 24 * 60 * 60 * 1000;
  const eliminados = [];

  // 1) Borrar por antigüedad
  for (const nombre of todos) {
    const ruta = path.join(config.BACKUP_DIR, nombre);
    try {
      const stat = fs.statSync(ruta);
      if (ahora - stat.mtimeMs > maxMs) {
        fs.unlinkSync(ruta);
        eliminados.push(nombre);
      }
    } catch (_) { /* ignorar si no se puede stat/borrar */ }
  }

  // 2) Borrar los más antiguos si superamos maxFiles
  const restantes = todos.filter((f) => !eliminados.includes(f));
  if (restantes.length > maxFiles) {
    const aBorrar = restantes.slice(0, restantes.length - maxFiles);
    for (const nombre of aBorrar) {
      try {
        fs.unlinkSync(path.join(config.BACKUP_DIR, nombre));
        eliminados.push(nombre);
      } catch (_) { /* ignorar */ }
    }
  }

  return eliminados;
}

/**
 * Flujo completo: crear backup + verificar integridad + aplicar retención.
 * Pensado para `npm run backup` o para llamar al arranque de la app.
 *
 * @param {Database} db
 * @param {string}   [contexto]
 * @param {object}   [retencionOpts]
 * @returns {Promise<{ ruta: string, integridadOk: boolean, eliminados: string[] }>}
 */
async function backupCompleto(db, contexto, retencionOpts) {
  const ruta = await crearBackup(db, contexto);
  const { ok: integridadOk, detail } = verificarIntegridad(ruta);
  if (!integridadOk) {
    console.warn(`[backup] AVISO: el backup ${path.basename(ruta)} NO pasó la verificación de integridad: ${detail}`);
  }
  const eliminados = aplicarRetencion(retencionOpts);
  return { ruta, integridadOk, eliminados };
}

module.exports = {
  crearBackup,
  verificarIntegridad,
  aplicarRetencion,
  backupCompleto,
};

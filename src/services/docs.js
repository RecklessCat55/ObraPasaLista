'use strict';
/**
 * services/docs.js — gestión de carpetas/archivos de documentación por
 * obra/partida (equivalente a las funciones _ruta_carpeta_obra y
 * _archivar_docs_partida de app.py, sección 3.3/4.6 del doc de cambios).
 */
const fs = require('fs');
const path = require('path');
const config = require('../config');
const { secureFilename } = require('../utils');

/** Ruta relativa (dentro de DOCS_DIR) de una carpeta nueva. */
function rutaCarpetaObra(idObra, nombreCarpeta, idCarpeta) {
  return path.join(`obra_${idObra}`, `carpeta_${idCarpeta}_${secureFilename(nombreCarpeta) || 'carpeta'}`);
}

/**
 * Mueve físicamente a docs/archivado/... toda la documentación asociada a
 * una partida (y sus subcarpetas) y marca esas carpetas como archivadas.
 * Se llama ANTES de borrar la partida: la FK id_partida de carpeta_obra es
 * ON DELETE SET NULL, así que al borrar la partida SQLite limpia esa
 * referencia automáticamente. Devuelve el nº de archivos movidos.
 */
function archivarDocsPartida(db, idObra, idPartida) {
  const carpetasRaiz = db
    .prepare('SELECT * FROM carpeta_obra WHERE id_partida=? AND archivada=0')
    .all(idPartida);
  if (!carpetasRaiz.length) return 0;

  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const fechaTag =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_` +
    `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const destinoRelBase = path.join('archivado', `obra_${idObra}`, `partida_${idPartida}_${fechaTag}`);
  fs.mkdirSync(path.join(config.DOCS_DIR, destinoRelBase), { recursive: true });

  // BFS: carpeta raíz + todas sus subcarpetas
  const todas = [];
  const pendientes = [...carpetasRaiz];
  const stmtHijas = db.prepare('SELECT * FROM carpeta_obra WHERE id_padre=? AND archivada=0');
  while (pendientes.length) {
    const c = pendientes.pop();
    todas.push(c);
    pendientes.push(...stmtHijas.all(c.id_carpeta));
  }

  let nArchivos = 0;
  const stmtArchivos = db.prepare('SELECT * FROM archivo_obra WHERE id_carpeta=?');
  const updArchivo = db.prepare('UPDATE archivo_obra SET ruta_relativa=? WHERE id_archivo=?');
  const updCarpeta = db.prepare('UPDATE carpeta_obra SET ruta_relativa=?, archivada=1 WHERE id_carpeta=?');

  for (const c of todas) {
    const origenAbs = path.join(config.DOCS_DIR, c.ruta_relativa);
    const destinoRel = path.join(destinoRelBase, path.basename(c.ruta_relativa));
    const destinoAbs = path.join(config.DOCS_DIR, destinoRel);
    try {
      if (fs.existsSync(origenAbs) && fs.statSync(origenAbs).isDirectory() && !fs.existsSync(destinoAbs)) {
        fs.mkdirSync(path.dirname(destinoAbs), { recursive: true });
        fs.renameSync(origenAbs, destinoAbs);
      }
    } catch (e) {
      // si ya no está en disco, seguimos para dejar la BD consistente
    }
    const archivos = stmtArchivos.all(c.id_carpeta);
    for (const a of archivos) {
      const nuevaRuta = path.join(destinoRel, path.basename(a.ruta_relativa));
      updArchivo.run(nuevaRuta, a.id_archivo);
      nArchivos += 1;
    }
    updCarpeta.run(destinoRel, c.id_carpeta);
  }
  return nArchivos;
}

module.exports = { rutaCarpetaObra, archivarDocsPartida };

'use strict';
/**
 * routes/documentacion.js — documentación por obra/partida: carpetas y
 * subida de archivos. Montado en '/obra' (con el mismo path en singular que
 * usaba la version Python, distinto de '/obras').
 */
const fs = require('fs');
const path = require('path');
const express = require('express');
const multer = require('multer');
const router = express.Router();
const db = require('../db');
const config = require('../config');
const { renderPage } = require('../middleware/render');
const { rutaCarpetaObra } = require('../services/docs');
const { secureFilename, ValidationError } = require('../utils');
const { chkObraActiva } = require('../services/negocio');

const EXTENSIONES_PERMITIDAS = new Set([
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
  '.odt', '.ods', '.odp',
  '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg',
  '.dwg', '.dxf',
  '.txt', '.csv', '.rtf',
  '.zip', '.7z', '.rar', '.tar', '.gz'
]);

const EXTENSIONES_PROHIBIDAS = new Set([
  '.exe', '.bat', '.cmd', '.sh', '.ps1', '.vbs', '.js', '.jar', '.msi', '.com', '.scr', '.pif'
]);

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 64 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const ext = path.extname(file.originalname || '').toLowerCase();
    if (EXTENSIONES_PROHIBIDAS.has(ext)) {
      return cb(new ValidationError(`Tipo de archivo ejecutable no permitido: ${ext}`));
    }
    if (!EXTENSIONES_PERMITIDAS.has(ext)) {
      return cb(new ValidationError(`Extensión de archivo no permitida (${ext}). Permitidas: PDF, Office, imágenes, CAD, texto y comprimidos.`));
    }
    cb(null, true);
  }
});

// Fallback equivalente a mimetypes.guess_type() de Python cuando el navegador
// no manda Content-Type para el archivo subido (poco común, pero posible).
const MIME_POR_EXT = {
  '.pdf': 'application/pdf',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.txt': 'text/plain',
  '.csv': 'text/csv',
  '.doc': 'application/msword',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.xls': 'application/vnd.ms-excel',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.dwg': 'image/vnd.dwg',
  '.zip': 'application/zip',
};
function guessMime(filename) {
  return MIME_POR_EXT[path.extname(filename).toLowerCase()] || null;
}

router.get('/:id_obra/documentacion', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  const obra = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(idObra);
  if (!obra) {
    req.flash('Obra no encontrada.', 'error');
    return res.redirect('/obras/');
  }

  const partidas = conn.prepare('SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo').all(idObra);
  const todasCarpetas = conn
    .prepare("SELECT * FROM carpeta_obra WHERE id_obra=? AND archivada=0 ORDER BY nombre")
    .all(idObra);
  const carpetasArchivadas = conn
    .prepare('SELECT * FROM carpeta_obra WHERE id_obra=? AND archivada=1 ORDER BY ruta_relativa')
    .all(idObra);
  const todosArchivos = conn
    .prepare(
      `SELECT a.* FROM archivo_obra a JOIN carpeta_obra c ON a.id_carpeta=c.id_carpeta
       WHERE c.id_obra=? ORDER BY a.nombre`
    )
    .all(idObra);

  const archivosPorCarpeta = {};
  for (const a of todosArchivos) {
    if (!archivosPorCarpeta[a.id_carpeta]) archivosPorCarpeta[a.id_carpeta] = [];
    archivosPorCarpeta[a.id_carpeta].push(a);
  }

  const subcarpetasPorPadre = {};
  const raizPorPartida = {};
  for (const c of todasCarpetas) {
    if (c.id_padre) {
      if (!subcarpetasPorPadre[c.id_padre]) subcarpetasPorPadre[c.id_padre] = [];
      subcarpetasPorPadre[c.id_padre].push(c);
    } else {
      const key = c.id_partida === null ? 'null' : c.id_partida;
      if (!raizPorPartida[key]) raizPorPartida[key] = [];
      raizPorPartida[key].push(c);
    }
  }

  const grupos = partidas.map((p) => ({ partida: p, carpetas: raizPorPartida[p.id_partida] || [] }));
  grupos.push({ partida: null, carpetas: raizPorPartida['null'] || [] }); // documentación general de la obra

  const partidaFoco = req.query.partida ? parseInt(req.query.partida, 10) : null;

  renderPage(req, res, 'documentacion/index', {
    title: `Documentación ${obra.nombre}`,
    active: 'mas',
    obra,
    partidas,
    grupos,
    subcarpetas_por_padre: subcarpetasPorPadre,
    archivos_por_carpeta: archivosPorCarpeta,
    todas_carpetas_sel: todasCarpetas,
    partida_foco: partidaFoco,
    carpetas_archivadas: carpetasArchivadas,
  });
});

router.post('/:id_obra/documentacion/carpeta/nueva', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  try {
    chkObraActiva(conn, idObra);
    const nombre = (req.body.nombre || '').trim();
    if (!nombre) throw new ValidationError('El nombre de la carpeta es obligatorio.');
    const idPartida = req.body.id_partida || null;
    const idPadre = req.body.id_padre || null;
    let idCarpeta;
    const tx = conn.transaction(() => {
      const cur = conn
        .prepare('INSERT INTO carpeta_obra(id_obra,id_partida,nombre,ruta_relativa,id_padre) VALUES(?,?,?,?,?)')
        .run(idObra, idPartida, nombre, '', idPadre);
      idCarpeta = cur.lastInsertRowid;
      const rutaRel = rutaCarpetaObra(idObra, nombre, idCarpeta);
      conn.prepare('UPDATE carpeta_obra SET ruta_relativa=? WHERE id_carpeta=?').run(rutaRel, idCarpeta);
      fs.mkdirSync(path.join(config.DOCS_DIR, rutaRel), { recursive: true });
    });
    tx();
    req.flash(`Carpeta "${nombre}" creada.`, 'success');
  } catch (e) {
    if (e instanceof ValidationError) {
      req.flash(e.message, 'error');
    } else {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  res.redirect(`/obra/${idObra}/documentacion`);
});

router.post('/:id_obra/documentacion/carpeta/:id_carpeta/subir', (req, res) => {
  const idObra = parseInt(req.params.id_obra, 10);
  const idCarpeta = parseInt(req.params.id_carpeta, 10);
  upload.any()(req, res, (err) => {
    if (err) {
      const msg = err.code === 'LIMIT_FILE_SIZE'
        ? 'Uno o más archivos superan el límite máximo permitido de 64 MB.'
        : (err.message || 'Error al procesar los archivos subidos.');
      req.flash(msg, 'error');
      return res.redirect(`/obra/${idObra}/documentacion`);
    }
    const conn = db.getDb();
    try {
      chkObraActiva(conn, idObra);
      const carpeta = conn.prepare('SELECT * FROM carpeta_obra WHERE id_carpeta=? AND id_obra=?').get(idCarpeta, idObra);
      if (!carpeta) throw new ValidationError('Carpeta no encontrada.');

      const files = req.files || (req.file ? [req.file] : []);
      if (!files.length) throw new ValidationError('Selecciona al menos un archivo para subir.');

      const destinoDir = path.join(config.DOCS_DIR, carpeta.ruta_relativa);
      fs.mkdirSync(destinoDir, { recursive: true });

      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const fechaSubida =
        `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
        `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

      const stmt = conn.prepare(
        'INSERT INTO archivo_obra(id_carpeta,nombre,ruta_relativa,tipo_mime,fecha_subida,notas) VALUES(?,?,?,?,?,?)'
      );

      const tx = conn.transaction((archivos) => {
        for (const f of archivos) {
          let nombreSeguro = secureFilename(f.originalname) || 'archivo';
          const ext = path.extname(nombreSeguro);
          const base = path.basename(nombreSeguro, ext);
          let destinoAbs = path.join(destinoDir, nombreSeguro);
          let i = 1;
          while (fs.existsSync(destinoAbs)) {
            nombreSeguro = `${base}_${i}${ext}`;
            destinoAbs = path.join(destinoDir, nombreSeguro);
            i += 1;
          }
          fs.writeFileSync(destinoAbs, f.buffer);
          const rutaRel = path.join(carpeta.ruta_relativa, nombreSeguro);
          const tipoMime = f.mimetype || guessMime(nombreSeguro);
          stmt.run(
            idCarpeta,
            f.originalname,
            rutaRel,
            tipoMime,
            fechaSubida,
            (req.body.notas || '').trim()
          );
        }
      });

      tx(files);

      if (files.length === 1) {
        req.flash(`Archivo "${files[0].originalname}" subido correctamente.`, 'success');
      } else {
        req.flash(`${files.length} archivos subidos correctamente a la carpeta "${carpeta.nombre}".`, 'success');
      }
    } catch (e) {
      if (e instanceof ValidationError) {
        req.flash(e.message, 'error');
      } else {
        req.flash(`Error al subir archivos: ${e.message}`, 'error');
      }
    }
    res.redirect(`/obra/${idObra}/documentacion`);
  });
});

module.exports = router;

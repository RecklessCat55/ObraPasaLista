'use strict';
/**
 * utils.js — utilidades varias sin encaje en un servicio concreto.
 */

/**
 * Equivalente a `ValueError` de Python: errores de validación de negocio
 * "limpios", pensados para mostrarse tal cual al usuario. Se usa para
 * replicar el patrón, repetido en casi toda la app original,
 *   except ValueError as e: flash(str(e), 'error')
 *   except Exception as e:  flash(f'Error: {e}', 'error')
 * Sin esta distinción, un error de negocio (p.ej. "mes cerrado") y un error
 * inesperado (p.ej. un fallo de SQL) acabarían mostrando el mismo prefijo
 * "Error: ", lo cual en el original solo ocurre para el segundo caso.
 */
class ValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ValidationError';
  }
}

/**
 * Equivalente aproximado a werkzeug.utils.secure_filename: quita rutas,
 * acentos y caracteres no seguros para nombres de fichero, colapsa
 * separadores y recorta puntos/guiones al principio/final.
 */
function secureFilename(filename) {
  if (!filename) return '';
  // Solo el nombre, sin ruta (por si el navegador manda una ruta completa)
  let name = filename.replace(/^.*[\\/]/, '');
  name = name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  name = name.replace(/[^A-Za-z0-9._-]+/g, '_');
  name = name.replace(/^[._-]+|[._-]+$/g, '');
  return name || '';
}

/**
 * Equivalente al filtro `|tojson` de Jinja2/Flask: JSON.stringify normal,
 * pero escapando '<', '>', '&' y comillas simples para que el resultado
 * pueda embeberse de forma segura dentro de un <script>...</script> sin
 * riesgo de que un valor con "</script>" rompa la página (XSS). También
 * escapa U+2028/U+2029, que son válidos en JSON pero rompen JS si aparecen
 * literales dentro de un <script>.
 */
function toJsonScript(value) {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/'/g, '\\u0027')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

module.exports = { secureFilename, toJsonScript, ValidationError };

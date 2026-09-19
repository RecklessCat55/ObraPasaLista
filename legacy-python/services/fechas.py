# -*- coding: utf-8 -*-
"""
services/fechas.py — helpers de fecha y formato compartidos.

Se extraen a un módulo propio (sin dependencias de app.py) para que tanto
app.py como el resto de módulos de services/ puedan usarlos sin generar
imports circulares.
"""
import re
import unicodedata
from datetime import datetime, date as date_type


def nf(f):
    """Normaliza cualquier tipo de fecha (-> datetime.date)."""
    if isinstance(f, datetime):
        return f.date()
    if isinstance(f, date_type):
        return f
    if isinstance(f, str):
        return datetime.strptime(f[:10], '%Y-%m-%d').date()
    raise TypeError(f'Tipo de fecha no soportado: {type(f)}')


def fs(f):
    return nf(f).strftime('%Y-%m-%d')   # -> 'YYYY-MM-DD'


def mes(f):
    return nf(f).strftime('%Y-%m')      # -> 'YYYY-MM'


def dia(f):
    return nf(f).day                    # -> int 1..31


def hhmm(h):
    if h is None:
        return '--'
    hi = int(h)
    m = round((h - hi) * 60)
    if m == 60:
        hi += 1
        m = 0
    return f'{hi:02d}:{m:02d}'


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Z0-9]+', '_', s.upper()).strip('_')

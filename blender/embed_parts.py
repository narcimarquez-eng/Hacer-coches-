"""Incrusta blender/car_parts.glb en la página como base64, dentro de <script id="carPartsGlb">.

Uso: python3 blender/embed_parts.py   (después de regenerar car_parts.glb con Blender)
La página sigue siendo un único archivo: funciona descargada en el móvil y en GitHub Pages.
"""
import base64
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = ROOT / 'Parametric Car 3D Studio (2).html'
GLB = ROOT / 'blender' / 'car_parts.glb'

data = base64.b64encode(GLB.read_bytes()).decode('ascii')
src = HTML.read_text(encoding='utf-8')
out, n = re.subn(r'(<script id="carPartsGlb" type="application/octet-stream">)[^<]*(</script>)',
                 lambda m: m.group(1) + data + m.group(2), src)
if n != 1:
    raise SystemExit('No se encontró la etiqueta <script id="carPartsGlb"> en la página')
HTML.write_text(out, encoding='utf-8')
print(f'{GLB.name}: {GLB.stat().st_size} bytes -> {len(data)} caracteres base64 incrustados')

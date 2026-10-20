"""Incrusta las piezas de Blender en la página como base64, dentro de <script id="carPartsGlb">.

Uso (después de regenerar car_parts.glb con Blender):
    npx gltfpack -i blender/car_parts.glb -o blender/car_parts.q.glb -kn -km -kv -vtf
    python3 blender/embed_parts.py

gltfpack cuantiza los vértices (KHR_mesh_quantization, que three.js lee sin decodificadores); las UV
quedan en coma flotante (-vtf) porque la app pone sus propios materiales, y el
archivo queda en un tercio menos. Si no existe car_parts.q.glb (o es más antiguo que car_parts.glb)
se incrusta el GLB original. La página sigue siendo un único archivo: funciona descargada en el
móvil y en GitHub Pages.
"""
import base64
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = ROOT / 'Parametric Car 3D Studio (2).html'
RAW = ROOT / 'blender' / 'car_parts.glb'
PACKED = ROOT / 'blender' / 'car_parts.q.glb'

GLB = PACKED if PACKED.exists() and PACKED.stat().st_mtime >= RAW.stat().st_mtime else RAW
if GLB is RAW and PACKED.exists():
    print('Aviso: car_parts.q.glb es más antiguo que car_parts.glb; se incrusta el original sin cuantizar')
data = base64.b64encode(GLB.read_bytes()).decode('ascii')
src = HTML.read_text(encoding='utf-8')
out, n = re.subn(r'(<script id="carPartsGlb" type="application/octet-stream">)[^<]*(</script>)',
                 lambda m: m.group(1) + data + m.group(2), src)
if n != 1:
    raise SystemExit('No se encontró la etiqueta <script id="carPartsGlb"> en la página')
HTML.write_text(out, encoding='utf-8')
print(f'{GLB.name}: {GLB.stat().st_size} bytes -> {len(data)} caracteres base64 incrustados')

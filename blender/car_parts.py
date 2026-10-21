"""Genera las piezas del coche (asientos y accesorios) y las exporta a car_parts.glb.

Uso (sin interfaz):
    blender -b --factory-startup --python blender/car_parts.py

Las coordenadas se escriben como en la app (three.js): x a la derecha, y hacia arriba y z hacia
delante (o hacia fuera de la cara del coche donde se monta la pieza). Cada pieza es un Empty
'part_<nombre>' con sus mallas hijas. El nombre del material de cada malla indica su papel
(paint, chrome, steel...) y la app lo sustituye por su propio material, así el color de la
carrocería y del cromo siguen saliendo del panel.
"""
import bpy
import bmesh
import math
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'car_parts.glb')

ROLES = {   # color solo para la vista previa en Blender
    'paint': (0.5, 0.52, 0.55), 'roof': (0.1, 0.1, 0.12), 'chrome': (0.9, 0.9, 0.92),
    'steel': (0.11, 0.11, 0.12), 'rubber': (0.05, 0.05, 0.05), 'carbon': (0.04, 0.04, 0.04),
    'alu': (0.72, 0.74, 0.77), 'glass': (0.1, 0.12, 0.14), 'light': (1.0, 1.0, 0.95),
    'dark': (0.03, 0.03, 0.03), 'leather': (0.15, 0.1, 0.07), 'red': (0.8, 0.05, 0.02),
    'trim': (0.9, 0.9, 0.92), 'plate': (1.0, 1.0, 1.0), 'mirror': (0.8, 0.82, 0.85),
    'plastic': (0.06, 0.06, 0.07), 'lens': (0.85, 0.9, 0.95), 'rim': (0.75, 0.76, 0.8),
    'dash': (0.06, 0.05, 0.05), 'wood': (0.3, 0.16, 0.06), 'ambient': (0.2, 0.4, 1.0), 'analog': (0.85, 0.85, 0.85),
    'screen': (0.03, 0.05, 0.15), 'screen_cluster': (0.03, 0.05, 0.15), 'screen_info': (0.03, 0.05, 0.15),
    'screen_wide': (0.03, 0.05, 0.15), 'screen_rear': (0.03, 0.05, 0.15),
    'brake': (0.35, 0.35, 0.36), 'light_red': (1.0, 0.05, 0.02), 'darkchrome': (0.22, 0.23, 0.26),
    'reflector': (0.45, 0.02, 0.02), 'gloss': (0.01, 0.01, 0.012), 'textured': (0.06, 0.06, 0.065),
    'amber': (1.0, 0.5, 0.05),
}


# --------------------------------------------------------------------------- geometría básica
class Geo:
    """Lista de vértices (x, y, z en coordenadas de la app) y caras."""
    def __init__(self, v=None, f=None):
        self.v = list(v or [])
        self.f = list(f or [])

    def merge(self, *others):
        for o in others:
            base = len(self.v)
            self.v += o.v
            self.f += [[i + base for i in face] for face in o.f]
        return self

    def map(self, fn):
        self.v = [fn(*p) for p in self.v]
        return self

    def move(self, dx=0.0, dy=0.0, dz=0.0):
        return self.map(lambda x, y, z: (x + dx, y + dy, z + dz))

    def scale(self, sx=1.0, sy=1.0, sz=1.0):
        return self.map(lambda x, y, z: (x * sx, y * sy, z * sz))

    def rot(self, axis, ang, pivot=(0.0, 0.0, 0.0)):
        c, s = math.cos(ang), math.sin(ang)
        px, py, pz = pivot

        def r(x, y, z):
            x, y, z = x - px, y - py, z - pz
            if axis == 'x':
                y, z = y * c - z * s, y * s + z * c
            elif axis == 'y':
                x, z = x * c + z * s, -x * s + z * c
            else:
                x, y = x * c - y * s, x * s + y * c
            return (x + px, y + py, z + pz)
        return self.map(r)


def box(sx, sy, sz, c=(0, 0, 0)):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = [(c[0] + i * hx, c[1] + j * hy, c[2] + k * hz) for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)]
    f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return Geo(v, f)


def lathe(profile, n=24, closed=True):
    """Revoluciona un perfil [(radio, z)] alrededor del eje z. closed: el perfil es un lazo."""
    v, f = [], []
    m = len(profile)
    for i in range(n):
        a = 2 * math.pi * i / n
        for r, z in profile:
            v.append((r * math.cos(a), r * math.sin(a), z))
    seg = m if closed else m - 1
    for i in range(n):
        i2 = (i + 1) % n
        for j in range(seg):
            j2 = (j + 1) % m
            f.append([i * m + j, i2 * m + j, i2 * m + j2, i * m + j2])
    return Geo(v, f)


def cyl(r, length, axis='z', c=(0, 0, 0), n=24, r2=None):
    r2 = r if r2 is None else r2
    g = lathe([(0.0, -length / 2), (r, -length / 2), (r2, length / 2), (0.0, length / 2)], n, closed=False)
    if axis == 'x':
        g.rot('y', math.pi / 2)
    elif axis == 'y':
        g.rot('x', -math.pi / 2)
    return g.move(*c)


def sphere(r, c=(0, 0, 0), n=20):
    prof = [(r * math.sin(math.pi * k / 10), -r * math.cos(math.pi * k / 10)) for k in range(11)]
    return lathe(prof, n, closed=False).move(*c)


def prism(outline, depth, plane='zy', c=(0, 0, 0)):
    """Extruye un contorno 2D. plane 'zy': perfil lateral (z, y) extruido en x;
    'xy': perfil frontal (x, y) extruido en z; 'xz': planta (x, z) extruida en y."""
    n = len(outline)
    v = []
    for side in (-depth / 2, depth / 2):
        for a, b in outline:
            if plane == 'zy':
                v.append((side, b, a))
            elif plane == 'xy':
                v.append((a, b, side))
            else:
                v.append((a, side, b))
    f = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        f.append([i, j, n + j, n + i])
    return Geo(v, f).move(*c)


def rounded_poly(points, radius, steps=5):
    """Redondea las esquinas de una polilínea abierta [(x, y, z)]."""
    out = [points[0]]
    for i in range(1, len(points) - 1):
        p0, p1, p2 = points[i - 1], points[i], points[i + 1]
        d0 = [p1[k] - p0[k] for k in range(3)]
        d1 = [p2[k] - p1[k] for k in range(3)]
        l0, l1 = math.sqrt(sum(x * x for x in d0)), math.sqrt(sum(x * x for x in d1))
        r = min(radius, l0 / 2, l1 / 2)
        a = [p1[k] - d0[k] / l0 * r for k in range(3)]
        b = [p1[k] + d1[k] / l1 * r for k in range(3)]
        for s in range(steps + 1):
            t = s / steps
            out.append(tuple((1 - t) ** 2 * a[k] + 2 * (1 - t) * t * p1[k] + t * t * b[k] for k in range(3)))
    out.append(points[-1])
    return out


def _sub(a, b): return [a[k] - b[k] for k in range(3)]
def _cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def _norm(a):
    l = math.sqrt(sum(x * x for x in a)) or 1.0
    return [x / l for x in a]


def sweep(path, section, up=(0.0, 1.0, 0.0)):
    """Barre una sección cerrada [(u, v)] a lo largo de path. Si up es None el marco se transporta
    (tubos con curvas en cualquier dirección); si no, v sigue a 'up' y u es horizontal."""
    n, m = len(path), len(section)
    v, f = [], []
    prev_n = None
    for i, p in enumerate(path):
        t = _norm(_sub(path[min(n - 1, i + 1)], path[max(0, i - 1)]))
        if up is not None:
            nu = _norm(_cross(t, up))
            nv = _norm(_cross(nu, t))
        else:
            if prev_n is None:
                ref = [0, 1, 0] if abs(t[1]) < 0.9 else [1, 0, 0]
                prev_n = _norm(_cross(t, ref))
            nu = _norm(_cross(_cross(t, prev_n), t))
            prev_n = nu
            nv = _norm(_cross(t, nu))
        for a, b in section:
            v.append(tuple(p[k] + nu[k] * a + nv[k] * b for k in range(3)))
    for i in range(n - 1):
        for j in range(m):
            j2 = (j + 1) % m
            f.append([i * m + j, i * m + j2, (i + 1) * m + j2, (i + 1) * m + j])
    f.append(list(range(m - 1, -1, -1)))
    f.append([(n - 1) * m + j for j in range(m)])
    return Geo(v, f)


def circle(r, n=12):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def rrect(w, h, r, steps=3):
    """Sección de rectángulo redondeado centrada (u en ancho, v en alto)."""
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for s in range(steps + 1):
            a = math.radians(a0 + 90 * s / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def tube(path, r, n=12):
    return sweep(path, circle(r, n), up=None)


# --------------------------------------------------------------------------- escena de Blender
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = {}
    for name, col in ROLES.items():
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*col, 1.0)
        m.use_nodes = True
        m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*col, 1.0)
        mats[name] = m
    return mats


MATS = {}


def part(name):
    root = bpy.data.objects.new('part_' + name, None)
    bpy.context.scene.collection.objects.link(root)
    return root


def mesh(root, name, geo, role, bevel=0.0, segments=3, smooth=40, keep_winding=False, uv=None):
    """Crea una malla hija de root. bevel redondea aristas; smooth es el ángulo de arista viva."""
    me = bpy.data.meshes.new(f'{root.name}_{name}')
    me.from_pydata([(x, -z, y) for (x, y, z) in geo.v], [], geo.f)   # app (y arriba) -> Blender (z arriba)
    me.validate()
    if not keep_winding:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    if uv:
        layer = me.uv_layers.new(name='UVMap')
        for poly in me.polygons:
            for li in poly.loop_indices:
                layer.data[li].uv = uv[me.loops[li].vertex_index]
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = root
    me.materials.append(MATS[role])
    if bevel:
        b = ob.modifiers.new('Bevel', 'BEVEL')
        b.width = bevel
        b.segments = segments
        b.limit_method = 'ANGLE'
        b.angle_limit = math.radians(45)
    s = ob.modifiers.new('EdgeSplit', 'EDGE_SPLIT')
    s.split_angle = math.radians(smooth)
    return ob


# --------------------------------------------------------------------------- asientos
def seat_front():
    root = part('seat_front')
    # Origen en el suelo bajo el centro del asiento, mirando hacia +z
    mesh(root, 'rails', box(0.03, 0.025, 0.56, (-0.19, 0.0125, 0.0)).merge(box(0.03, 0.025, 0.56, (0.19, 0.0125, 0.0))), 'steel', 0.006)
    mesh(root, 'base', box(0.40, 0.14, 0.44, (0, 0.095, 0.0)), 'dark', 0.02)
    cushion = box(0.44, 0.11, 0.50, (0, 0.245, 0.02))
    bolsters = box(0.07, 0.12, 0.48, (-0.235, 0.27, 0.02)).merge(box(0.07, 0.12, 0.48, (0.235, 0.27, 0.02)))
    mesh(root, 'cushion', cushion, 'leather', 0.045, 4)
    mesh(root, 'cushion_bolsters', bolsters, 'leather', 0.03, 4)
    # Respaldo inclinado hacia atrás desde la parte trasera del cojín
    pivot = (0, 0.29, -0.21)
    back = box(0.46, 0.62, 0.11, (0, 0.29 + 0.31, -0.21))
    back_b = box(0.08, 0.52, 0.15, (-0.23, 0.29 + 0.28, -0.20)).merge(box(0.08, 0.52, 0.15, (0.23, 0.29 + 0.28, -0.20)))
    head = box(0.27, 0.20, 0.10, (0, 0.29 + 0.62 + 0.14, -0.205))
    posts = cyl(0.007, 0.10, 'y', (-0.07, 0.29 + 0.65, -0.205), 10).merge(cyl(0.007, 0.10, 'y', (0.07, 0.29 + 0.65, -0.205), 10))
    lean = -0.26
    mesh(root, 'back', back.rot('x', lean, pivot), 'leather', 0.045, 4)
    mesh(root, 'back_bolsters', back_b.rot('x', lean, pivot), 'leather', 0.035, 4)
    mesh(root, 'headrest', head.rot('x', lean, pivot), 'leather', 0.045, 4)
    mesh(root, 'posts', posts.rot('x', lean, pivot), 'chrome')


def seat_rear():
    root = part('seat_rear')
    # Banqueta de dos plazas y media, ancho de diseño 1.30 m
    mesh(root, 'base', box(1.20, 0.18, 0.46, (0, 0.10, 0.0)), 'dark', 0.02)
    cushion = Geo()
    for x in (-0.36, 0.36):
        cushion.merge(box(0.52, 0.11, 0.48, (x, 0.25, 0.02)))
    cushion.merge(box(0.22, 0.10, 0.46, (0, 0.245, 0.02)))
    mesh(root, 'cushion', cushion, 'leather', 0.04, 4)
    pivot = (0, 0.30, -0.20)
    back = Geo()
    for x in (-0.36, 0.36):
        back.merge(box(0.52, 0.58, 0.12, (x, 0.30 + 0.29, -0.20)))
    back.merge(box(0.22, 0.54, 0.11, (0, 0.30 + 0.27, -0.205)))
    heads = Geo()
    posts = Geo()
    for x in (-0.36, 0.36):
        heads.merge(box(0.25, 0.17, 0.09, (x, 0.30 + 0.58 + 0.12, -0.205)))
        posts.merge(cyl(0.007, 0.08, 'y', (x - 0.07, 0.30 + 0.61, -0.205), 10), cyl(0.007, 0.08, 'y', (x + 0.07, 0.30 + 0.61, -0.205), 10))
    mesh(root, 'back', back.rot('x', -0.22, pivot), 'leather', 0.04, 4)
    mesh(root, 'headrests', heads.rot('x', -0.22, pivot), 'leather', 0.04, 4)
    mesh(root, 'posts', posts.rot('x', -0.22, pivot), 'chrome')


# --------------------------------------------------------------------------- retrovisores (lado derecho, +x hacia fuera)
def mirrors():
    r = part('mirror_standard')
    mesh(r, 'arm', box(0.11, 0.035, 0.05, (0.055, 0.0, 0.0)), 'paint', 0.012)
    mesh(r, 'housing', box(0.21, 0.12, 0.09, (0.19, 0.03, -0.005)), 'paint', 0.04, 4)
    mesh(r, 'glass', box(0.18, 0.095, 0.006, (0.19, 0.03, -0.052)), 'mirror', 0.002)

    r = part('mirror_sport')
    mesh(r, 'arm', box(0.11, 0.02, 0.06, (0.055, -0.005, 0.0)), 'carbon', 0.008)
    housing = box(0.19, 0.085, 0.08, (0.18, 0.025, 0.0)).map(lambda x, y, z: (x, y, z * (1.0 - 0.35 * max(0.0, (x - 0.09) / 0.19))))
    mesh(r, 'housing', housing, 'paint', 0.035, 4)
    mesh(r, 'glass', box(0.165, 0.065, 0.006, (0.18, 0.025, -0.042)), 'mirror', 0.002)

    r = part('mirror_camera')
    mesh(r, 'arm', box(0.09, 0.025, 0.03, (0.045, 0.0, 0.0)), 'carbon', 0.008)
    mesh(r, 'pod', box(0.12, 0.04, 0.055, (0.13, 0.0, 0.0)), 'carbon', 0.016, 4)
    mesh(r, 'lens', cyl(0.009, 0.01, 'z', (0.17, 0.0, -0.03), 16), 'glass')

    r = part('mirror_classic')
    mesh(r, 'stalk', tube(rounded_poly([(0.0, -0.02, 0.0), (0.06, 0.0, 0.0), (0.10, 0.07, 0.0)], 0.03), 0.008, 10), 'chrome')
    mesh(r, 'head', cyl(0.065, 0.03, 'z', (0.12, 0.09, 0.0), 32), 'chrome', 0.008)
    mesh(r, 'glass', cyl(0.058, 0.004, 'z', (0.12, 0.09, -0.016), 32), 'mirror')


# --------------------------------------------------------------------------- manillas (lado derecho, +x hacia fuera)
def handles():
    r = part('handle_bar')
    mesh(r, 'recess', box(0.004, 0.045, 0.20, (0.002, 0, 0)), 'dark', 0.002)
    mesh(r, 'bar', box(0.024, 0.03, 0.18, (0.012, 0, 0)), 'trim', 0.011, 4)

    r = part('handle_pull')
    mesh(r, 'bar', box(0.018, 0.024, 0.20, (0.04, 0, 0)), 'trim', 0.009, 4)
    mesh(r, 'posts', box(0.04, 0.016, 0.022, (0.02, 0, 0.085)).merge(box(0.04, 0.016, 0.022, (0.02, 0, -0.085))), 'trim', 0.006)

    r = part('handle_classic')
    mesh(r, 'lever', box(0.02, 0.026, 0.14, (0.012, 0, -0.01)), 'trim', 0.009, 4)
    mesh(r, 'lock', cyl(0.012, 0.014, 'x', (0.007, 0, 0.09), 20), 'trim', 0.003)

    r = part('handle_popout')
    mesh(r, 'recess', box(0.004, 0.036, 0.17, (0.002, 0, 0)), 'dark', 0.002)
    mesh(r, 'paddle', box(0.012, 0.02, 0.12, (0.008, 0, 0)), 'trim', 0.005)

    r = part('handle_flush')
    mesh(r, 'plate', box(0.005, 0.022, 0.16, (0.0025, 0, 0)), 'trim', 0.002)


# --------------------------------------------------------------------------- alerones (origen en el borde trasero del maletero)
def spoilers():
    r = part('spoiler_lip')
    mesh(r, 'lip', prism([(0.10, 0.0), (-0.02, 0.0), (-0.025, 0.045)], 1.60), 'paint', 0.01)

    r = part('spoiler_ducktail')
    mesh(r, 'tail', prism([(0.30, 0.0), (-0.03, 0.0), (-0.05, 0.095), (0.10, 0.045)], 1.55), 'paint', 0.02, 4)

    r = part('spoiler_wing')
    chord, t = 0.30, 0.13
    up, low = [], []
    for k in range(16):
        x = (1 - math.cos(math.pi * k / 15)) / 2
        yt = 5 * t * chord * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        z = chord / 2 - x * chord
        up.append((z, yt))
        low.append((z, -yt))
    foil = up + low[-2:0:-1]
    wing = prism(foil, 1.50).rot('x', 0.10).move(0, 0.33, 0.08)
    mesh(r, 'wing', wing, 'carbon', 0.004)
    ends = box(0.012, 0.16, 0.36, (-0.755, 0.33, 0.07)).merge(box(0.012, 0.16, 0.36, (0.755, 0.33, 0.07)))
    mesh(r, 'endplates', ends, 'carbon', 0.004)
    legs = Geo()
    for x in (-0.45, 0.45):
        legs.merge(prism([(0.06, 0.0), (-0.04, 0.0), (0.02, 0.33), (0.10, 0.33)], 0.025, 'zy', (x, 0, 0)))
    mesh(r, 'uprights', legs, 'carbon', 0.006)

    r = part('spoiler_roof')
    mesh(r, 'roof', prism([(0.08, 0.0), (-0.20, -0.025), (-0.20, 0.012), (0.08, 0.032)], 1.40), 'roof', 0.01)


# --------------------------------------------------------------------------- paragolpes (origen en la cara del coche, +z hacia fuera, ancho 1.90)
def bumper_path(half=0.95, wrap=0.14, z0=0.01):
    pts = []
    c = half - wrap
    for k in range(7):
        a = math.radians(180 - 90 * k / 6)
        pts.append((-c + wrap * math.cos(a), 0.0, z0 - wrap + wrap * math.sin(a)))
    for k in range(1, 8):
        pts.append((-c + 2 * c * k / 8, 0.0, z0))
    for k in range(7):
        a = math.radians(90 - 90 * k / 6)
        pts.append((c + wrap * math.cos(a), 0.0, z0 - wrap + wrap * math.sin(a)))
    return pts


def bumpers():
    r = part('bumper_chrome')
    mesh(r, 'blade', sweep(bumper_path(), [(0.0, -0.035), (0.06, -0.035), (0.08, -0.015), (0.08, 0.015), (0.06, 0.035), (0.0, 0.035)]), 'chrome', 0.006)
    mesh(r, 'rubber', sweep(bumper_path(0.90, 0.10), [(0.079, -0.009), (0.086, -0.009), (0.086, 0.009), (0.079, 0.009)]), 'rubber')
    guards = box(0.06, 0.14, 0.07, (-0.50, 0.01, 0.10)).merge(box(0.06, 0.14, 0.07, (0.50, 0.01, 0.10)))
    mesh(r, 'guards', guards, 'chrome', 0.022, 4)

    r = part('bumper_american')
    mesh(r, 'bar', sweep(bumper_path(0.98, 0.18), [(0.0, -0.07), (0.11, -0.07), (0.14, -0.035), (0.14, 0.035), (0.11, 0.07), (0.0, 0.07)]), 'chrome', 0.01)
    mesh(r, 'rubber', sweep(bumper_path(0.93, 0.13), [(0.138, -0.014), (0.148, -0.014), (0.148, 0.014), (0.138, 0.014)]), 'rubber')
    guards, tips = Geo(), Geo()
    for x in (-0.57, 0.57):
        guards.merge(box(0.08, 0.26, 0.09, (x, 0.03, 0.17)))
        tips.merge(box(0.085, 0.05, 0.095, (x, 0.14, 0.17)))
    mesh(r, 'guards', guards, 'chrome', 0.03, 4)
    mesh(r, 'tips', tips, 'rubber', 0.015)

    r = part('splitter')       # origen a ras del bajo de la carrocería
    mesh(r, 'blade', prism([(-0.83, 0.0), (0.83, 0.0), (0.91, -0.08), (-0.91, -0.08)], 0.018, 'xz', (0, 0, 0.10)), 'carbon', 0.004)
    fins = Geo()
    for x in (-0.48, 0.0, 0.48):
        fins.merge(prism([(0.12, 0.0), (-0.02, 0.0), (-0.02, 0.05), (0.04, 0.05)], 0.012, 'zy', (x, 0.009, 0)))
    mesh(r, 'fins', fins, 'carbon', 0.002)

    r = part('canards')        # origen a la altura del paragolpes
    blades = Geo()
    for s in (-1, 1):
        blade = prism([(0.0, 0.0), (s * 0.16, 0.0), (s * 0.12, 0.10), (0.0, 0.10)], 0.012, 'xz')
        blades.merge(blade.rot('y', -s * 0.35).rot('z', s * 0.3).move(s * 0.80, 0.07, 0.0))
    mesh(r, 'blades', blades, 'carbon', 0.003)

    r = part('diffuser')       # trasero, modelado hacia +z (la app lo gira)
    mesh(r, 'plate', box(1.52, 0.02, 0.30, (0, 0, -0.06)), 'carbon', 0.005)
    fins = Geo()
    for k in range(-2, 3):
        fins.merge(prism([(0.09, 0.0), (-0.21, 0.0), (-0.21, 0.02), (0.09, 0.09)], 0.012, 'zy', (k * 0.285, 0.01, 0)))
    mesh(r, 'fins', fins, 'carbon', 0.002)

    r = part('skidplate')
    mesh(r, 'plate', box(1.10, 0.015, 0.36, (0, 0, 0)), 'alu', 0.006)
    mesh(r, 'bolts', Geo().merge(*[cyl(0.012, 0.006, 'y', (x, 0.009, z), 12) for x in (-0.45, 0.45) for z in (-0.12, 0.12)]), 'steel')

    steel_profile = [(0.0, -0.085), (0.15, -0.085), (0.18, -0.045), (0.18, 0.045), (0.15, 0.085), (0.0, 0.085)]
    hooks = Geo()
    for x in (-0.60, 0.60):
        hooks.merge(tube([(x + 0.035 * math.cos(math.pi * k / 10), -0.03 + 0.035 * math.sin(math.pi * k / 10), 0.20) for k in range(11)], 0.011, 10))

    r = part('bumper_offroad_front')
    mesh(r, 'bar', sweep(bumper_path(0.96, 0.06, 0.0), steel_profile), 'steel', 0.012)
    mesh(r, 'hooks', Geo().merge(hooks), 'red')
    mesh(r, 'winch', box(0.36, 0.11, 0.12, (0, 0.135, 0.06)), 'steel', 0.012)
    mesh(r, 'drum', cyl(0.042, 0.24, 'x', (0, 0.135, 0.13), 20), 'dark')
    mesh(r, 'fairlead', box(0.16, 0.05, 0.012, (0, 0.135, 0.18)), 'chrome', 0.004)

    r = part('bumper_offroad_rear')
    mesh(r, 'bar', sweep(bumper_path(0.96, 0.06, 0.0), steel_profile), 'steel', 0.012)
    mesh(r, 'hooks', Geo().merge(hooks), 'red')

    r = part('hitch')
    mesh(r, 'receiver', box(0.07, 0.07, 0.30, (0, -0.06, 0.10)), 'steel', 0.008)
    mesh(r, 'mount', box(0.06, 0.03, 0.10, (0, -0.03, 0.24)), 'steel', 0.006)
    mesh(r, 'ball', sphere(0.026, (0, 0.035, 0.26)).merge(cyl(0.012, 0.05, 'y', (0, 0.0, 0.26), 14)), 'chrome')

    r = part('bumper_step')
    mesh(r, 'bar', sweep(bumper_path(0.94, 0.08), [(0.0, -0.05), (0.10, -0.05), (0.12, -0.03), (0.12, 0.05), (0.0, 0.05)]), 'chrome', 0.01)
    pad = box(0.76, 0.012, 0.11, (0, 0.056, 0.065))
    for k in range(9):
        pad.merge(box(0.74, 0.006, 0.006, (0, 0.064, 0.02 + k * 0.011)))
    mesh(r, 'pad', pad, 'rubber')

    r = part('bullbar')        # origen a la altura del paragolpes
    tr = 0.03
    hoop = rounded_poly([(-0.42, -0.10, 0.12), (-0.42, 0.40, 0.17), (0.42, 0.40, 0.17), (0.42, -0.10, 0.12)], 0.10, 6)
    bars = Geo().merge(tube(hoop, tr, 12), tube([(-0.42, 0.12, 0.148), (0.42, 0.12, 0.148)], tr * 0.8, 12))
    for s in (-1, 1):
        bars.merge(tube(rounded_poly([(s * 0.42, -0.02, 0.13), (s * 0.72, -0.02, 0.09), (s * 0.86, -0.02, 0.0)], 0.10, 5), tr * 0.8, 12))
    mesh(r, 'tubes', bars, 'steel')
    mesh(r, 'mounts', box(0.08, 0.06, 0.14, (-0.42, -0.10, 0.06)).merge(box(0.08, 0.06, 0.14, (0.42, -0.10, 0.06))), 'steel', 0.01)

    r = part('rally_lamps')    # origen en el centro de los faros
    mesh(r, 'bar', tube([(-0.70, -0.10, 0.10), (0.70, -0.10, 0.10)], 0.018, 12), 'steel')
    shells, lenses, guards, mounts = Geo(), Geo(), Geo(), Geo()
    for x in (-0.42, 0.42):
        shells.merge(lathe([(0.0, -0.06), (0.06, -0.06), (0.085, 0.0), (0.088, 0.035), (0.08, 0.04), (0.0, 0.04)], 32, closed=False).move(x, 0, 0.14))
        lenses.merge(cyl(0.076, 0.006, 'z', (x, 0, 0.181), 32))
        guards.merge(box(0.15, 0.012, 0.01, (x, 0, 0.19)).rot('z', 0.785, (x, 0, 0.19)), box(0.15, 0.012, 0.01, (x, 0, 0.19)).rot('z', -0.785, (x, 0, 0.19)))
        mounts.merge(tube([(x, -0.10, 0.10), (x, -0.05, 0.12)], 0.012, 10))
    mesh(r, 'shells', shells, 'steel')
    mesh(r, 'lenses', lenses, 'light')
    mesh(r, 'guards', guards, 'dark', 0.002)
    mesh(r, 'mounts', mounts, 'steel')


# --------------------------------------------------------------------------- escapes (origen en la cara, +z hacia fuera)
def exhausts():
    r = part('exhaust_round')       # radio de diseño 0.05
    mesh(r, 'tip', lathe([(0.050, -0.12), (0.050, 0.0), (0.056, 0.014), (0.056, 0.030), (0.051, 0.037), (0.044, 0.031), (0.042, -0.02), (0.042, -0.12)], 32), 'chrome')
    mesh(r, 'inner', cyl(0.042, 0.01, 'z', (0, 0, -0.02), 32), 'dark')

    r = part('exhaust_rect')        # 0.20 x 0.07
    frame = Geo().merge(box(0.20, 0.014, 0.06, (0, 0.028, 0)), box(0.20, 0.014, 0.06, (0, -0.028, 0)),
                        box(0.014, 0.07, 0.06, (-0.093, 0, 0)), box(0.014, 0.07, 0.06, (0.093, 0, 0)))
    mesh(r, 'frame', frame, 'chrome', 0.005)
    mesh(r, 'inner', box(0.175, 0.045, 0.01, (0, 0, -0.015)), 'dark')


# --------------------------------------------------------------------------- detalles de techo, capó y frontal
def small_parts():
    r = part('antenna_shark')      # origen en la superficie del techo, punta hacia +z
    fin = prism([(0.10, 0.0), (0.06, 0.012), (0.0, 0.038), (-0.05, 0.062), (-0.078, 0.058), (-0.088, 0.0)], 0.05)
    mesh(r, 'fin', fin, 'roof', 0.018, 4)

    r = part('hood_scoop')          # origen en la superficie del capó
    mesh(r, 'body', prism([(0.22, 0.0), (0.21, 0.075), (-0.08, 0.05), (-0.22, 0.0)], 0.44), 'paint', 0.03, 4)
    mesh(r, 'mouth', box(0.34, 0.042, 0.03, (0, 0.04, 0.205)), 'dark', 0.006)

    r = part('hood_vent')           # una rejilla; la app pone dos en espejo
    mesh(r, 'frame', box(0.24, 0.012, 0.18, (0, 0.006, 0)), 'dark', 0.006)
    slats = Geo()
    for k in range(5):
        slats.merge(box(0.21, 0.004, 0.03, (0, 0.012, -0.06 + k * 0.03)).rot('x', -0.5, (0, 0.012, -0.06 + k * 0.03)))
    mesh(r, 'slats', slats, 'steel')

    r = part('hood_bulge')          # largo de diseño 0.90
    mesh(r, 'bulge', prism([(0.45, 0.0), (0.28, 0.03), (-0.30, 0.045), (-0.45, 0.0)], 0.56), 'paint', 0.035, 4)

    r = part('fog_round')
    mesh(r, 'bezel', lathe([(0.040, 0.0), (0.053, 0.0), (0.055, 0.010), (0.050, 0.014), (0.042, 0.010)], 32), 'chrome')
    mesh(r, 'lens', cyl(0.041, 0.02, 'z', (0, 0, 0.0), 32), 'light')
    mesh(r, 'housing', cyl(0.05, 0.10, 'z', (0, 0, -0.06), 24), 'dark')

    r = part('fog_strip')
    mesh(r, 'frame', box(0.19, 0.036, 0.03, (0, 0, -0.008)), 'dark', 0.008)
    mesh(r, 'lens', box(0.16, 0.018, 0.02, (0, 0, 0.004)), 'light', 0.006)


def new_parts():
    r = part('roof_box')            # cofre de techo, origen en la base
    shell = prism([(0.76, 0.05), (0.66, 0.22), (0.35, 0.33), (-0.55, 0.345), (-0.76, 0.27), (-0.76, 0.05)], 0.80)
    mesh(r, 'shell', shell, 'plastic', 0.10, 5)
    mesh(r, 'seam', box(0.82, 0.008, 1.40, (0, 0.20, -0.02)), 'dark')
    feet = Geo().merge(*[box(0.07, 0.05, 0.10, (x, 0.025, z)) for x in (-0.30, 0.30) for z in (-0.45, 0.45)])
    mesh(r, 'feet', feet, 'dark', 0.01)

    r = part('roof_lightbar')       # barra LED de techo, origen en la base
    mesh(r, 'housing', prism([(0.045, 0.0), (0.045, 0.075), (-0.035, 0.075), (-0.05, 0.0)], 1.00, 'zy', (0, 0.03, 0)), 'dark', 0.012)
    mesh(r, 'lens', box(0.96, 0.05, 0.006, (0, 0.067, 0.048)), 'light', 0.002)
    mesh(r, 'brackets', box(0.03, 0.06, 0.06, (-0.42, 0.0, -0.005)).merge(box(0.03, 0.06, 0.06, (0.42, 0.0, -0.005))), 'steel', 0.006)

    r = part('spare_wheel')         # origen en la cara trasera, rueda hacia +z (radio de diseño 0.36)
    tire = lathe([(0.22, -0.11), (0.33, -0.12), (0.36, -0.08), (0.36, 0.08), (0.33, 0.12), (0.22, 0.11)], 48)
    mesh(r, 'tire', tire.move(0, 0, 0.16), 'rubber', 0.0, 3, 25)
    mesh(r, 'rim', lathe([(0.0, 0.10), (0.22, 0.10), (0.22, -0.08), (0.0, -0.08)], 40, closed=False).move(0, 0, 0.16), 'alu')
    mesh(r, 'hub', cyl(0.06, 0.03, 'z', (0, 0, 0.27), 24), 'chrome', 0.006)
    mesh(r, 'bracket', box(0.30, 0.06, 0.06, (0, 0, 0.03)), 'steel', 0.008)

    r = part('snorkel')             # altura de diseño 1.0; origen en la base sobre la aleta
    pipe = rounded_poly([(0, 0.0, 0.0), (0, 0.86, 0.0), (0, 0.96, 0.08)], 0.08, 6)
    mesh(r, 'pipe', sweep(pipe, rrect(0.09, 0.10, 0.03), up=None), 'plastic')
    mesh(r, 'head', box(0.12, 0.11, 0.16, (0, 0.97, 0.10)), 'plastic', 0.035, 4)
    mesh(r, 'intake', box(0.10, 0.07, 0.005, (0, 0.97, 0.181)), 'dark')
    mesh(r, 'base', box(0.14, 0.02, 0.16, (0, 0.01, 0.0)), 'plastic', 0.008)

    r = part('mud_flap')            # origen en el borde superior
    mesh(r, 'flap', box(0.30, 0.32, 0.012, (0, -0.16, 0)), 'rubber', 0.008)
    mesh(r, 'bracket', box(0.30, 0.025, 0.03, (0, 0.0, 0.0)), 'steel', 0.005)

    r = part('license_plate')       # origen detrás de la placa, cara hacia +z
    w, h = 0.52, 0.11
    face = Geo([(-w / 2, -h / 2, 0.009), (w / 2, -h / 2, 0.009), (w / 2, h / 2, 0.009), (-w / 2, h / 2, 0.009)], [[0, 1, 2, 3]])
    mesh(r, 'face', face, 'plate', keep_winding=True, uv=[(0, 0), (1, 0), (1, 1), (0, 1)])
    mesh(r, 'back', box(w, h, 0.006, (0, 0, 0.005)), 'dark')
    frame = Geo().merge(box(w + 0.03, 0.015, 0.014, (0, h / 2 + 0.0075, 0.007)), box(w + 0.03, 0.015, 0.014, (0, -h / 2 - 0.0075, 0.007)),
                        box(0.015, h, 0.014, (-w / 2 - 0.0075, 0, 0.007)), box(0.015, h, 0.014, (w / 2 + 0.0075, 0, 0.007)))
    mesh(r, 'frame', frame, 'dark', 0.004)


# --------------------------------------------------------------------------- módulos de faro (origen en el frente, mirando a +z)
def lamp_parts():
    r = part('lamp_projector')      # proyector LED, radio de diseño 0.04
    cup = lathe([(0.040, 0.0), (0.026, -0.034), (0.023, -0.036), (0.037, 0.0)], 40)
    mesh(r, 'cup', cup, 'chrome', 0.0, 3, 30)
    mesh(r, 'barrel', cyl(0.024, 0.045, 'z', (0, 0, -0.056), 32), 'dark', 0.003)
    mesh(r, 'glow', cyl(0.019, 0.004, 'z', (0, 0, -0.026), 32), 'light')
    dome = lathe([(0.0, -0.004), (0.010, -0.006), (0.018, -0.011), (0.022, -0.018), (0.022, -0.022), (0.0, -0.022)], 32)
    mesh(r, 'lens', dome, 'lens', 0.0, 3, 60)
    mesh(r, 'ring', lathe([(0.0315 + 0.0022 * math.cos(a), -0.010 + 0.0022 * math.sin(a))
                           for a in [2 * math.pi * k / 10 for k in range(10)]], 40), 'light', 0.0, 3, 80)

    r = part('lamp_reflector')      # parábola clásica con bombilla, radio de diseño 0.06
    outer = [(0.060 * t, -0.05 * (1 - t * t)) for t in [k / 8 for k in range(9)]]
    inner = [(rr, z - 0.003) for rr, z in reversed(outer)]
    mesh(r, 'bowl', lathe(outer[1:] + inner[:-1], 48), 'chrome', 0.0, 3, 50)
    mesh(r, 'bulb', sphere(0.011, (0, 0, -0.030), 16), 'light')
    mesh(r, 'cap', cyl(0.007, 0.006, 'z', (0, 0, -0.017), 16), 'chrome')
    mesh(r, 'socket', cyl(0.016, 0.03, 'z', (0, 0, -0.06), 20), 'dark')

    r = part('lamp_led_cell')       # celda LED rectangular 0.05 x 0.022
    mesh(r, 'frame', box(0.050, 0.022, 0.030, (0, 0, -0.016)), 'dark', 0.003)
    mesh(r, 'face', box(0.040, 0.013, 0.004, (0, 0, -0.002)), 'light', 0.0015)
    mesh(r, 'lip', box(0.052, 0.003, 0.004, (0, 0.0105, -0.002)), 'chrome')


# --------------------------------------------------------------------------- tapacubos (radio de diseño 0.20, origen detrás, cara hacia +z)
def ring_of(geo_fn, n, radius, z=0.0, phase=0.0):
    """n copias de una pieza repartidas en círculo (la pieza se crea apuntando a +x)."""
    out = Geo()
    for k in range(n):
        a = phase + 2 * math.pi * k / n
        out.merge(geo_fn().move(radius, 0, z).rot('z', a))
    return out


def hubcaps():
    r = part('hubcap_aero')         # disco aerodinámico de eléctrico
    disc = lathe([(0.0, 0.0), (0.20, 0.0), (0.20, 0.006), (0.185, 0.014), (0.12, 0.022), (0.0, 0.024)], 64, closed=False)
    mesh(r, 'disc', disc, 'rim', 0.0, 3, 30)
    mesh(r, 'slots', ring_of(lambda: box(0.075, 0.016, 0.006), 5, 0.14, 0.0185), 'dark', 0.003)
    mesh(r, 'cap', cyl(0.036, 0.008, 'z', (0, 0, 0.026), 32), 'chrome', 0.002)

    r = part('hubcap_classic')      # tapacubos cromado con ranuras
    dome = lathe([(0.0, 0.0), (0.20, 0.0), (0.20, 0.008), (0.17, 0.016), (0.09, 0.030), (0.0, 0.034)], 64, closed=False)
    mesh(r, 'dome', dome, 'alu', 0.0, 3, 30)
    mesh(r, 'slots', ring_of(lambda: box(0.05, 0.012, 0.006).rot('y', -0.18), 10, 0.15, 0.0135), 'dark', 0.002)
    mesh(r, 'badge', cyl(0.032, 0.006, 'z', (0, 0, 0.035), 32), 'dark', 0.002)
    mesh(r, 'badge_ring', lathe([(0.034 + 0.003 * math.cos(a), 0.035 + 0.003 * math.sin(a)) for a in [2 * math.pi * k / 8 for k in range(8)]], 32), 'chrome')

    r = part('hubcap_turbine')      # turbina de álabes
    mesh(r, 'base', cyl(0.195, 0.006, 'z', (0, 0, 0.003), 64), 'dark')
    mesh(r, 'blades', ring_of(lambda: box(0.13, 0.010, 0.022).rot('x', 0.45), 14, 0.125, 0.014), 'rim', 0.002)
    mesh(r, 'rim_ring', lathe([(0.19, 0.0), (0.20, 0.0), (0.20, 0.016), (0.19, 0.016)], 64), 'chrome', 0.0, 3, 30)
    mesh(r, 'cone', lathe([(0.0, 0.0), (0.06, 0.0), (0.05, 0.02), (0.02, 0.034), (0.0, 0.036)], 32, closed=False), 'chrome')

    r = part('hubcap_moon')         # disco cromado liso (retro)
    mesh(r, 'disc', lathe([(0.0, 0.0), (0.20, 0.0), (0.20, 0.006), (0.15, 0.030), (0.07, 0.042), (0.0, 0.045)], 64, closed=False), 'alu', 0.0, 3, 30)
    mesh(r, 'badge', cyl(0.02, 0.004, 'z', (0, 0, 0.046), 24), 'dark')

    r = part('hubcap_steelie')      # llanta de chapa con tapa central
    disc = lathe([(0.0, 0.004), (0.10, 0.004), (0.12, 0.012), (0.16, 0.012), (0.18, 0.004), (0.20, 0.004), (0.20, 0.0), (0.0, 0.0)], 64)
    mesh(r, 'disc', disc, 'steel', 0.0, 3, 30)
    mesh(r, 'holes', ring_of(lambda: cyl(0.016, 0.004, 'z', (0, 0, 0.0125), 20), 8, 0.14, 0.0, math.pi / 8), 'dark')
    mesh(r, 'cap', lathe([(0.0, 0.0), (0.05, 0.0), (0.048, 0.012), (0.03, 0.024), (0.0, 0.027)], 32, closed=False).move(0, 0, 0.004), 'chrome')
    mesh(r, 'nuts', ring_of(lambda: cyl(0.009, 0.014, 'z', (0, 0, 0.011), 6), 5, 0.075), 'chrome')


# --------------------------------------------------------------------------- aerodinámica agresiva
def naca(chord, t, n=16):
    """Perfil alar NACA simétrico [(z, y)] con el borde de ataque en +z."""
    up, low = [], []
    for k in range(n):
        x = (1 - math.cos(math.pi * k / (n - 1))) / 2
        yt = 5 * t * chord * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        z = chord / 2 - x * chord
        up.append((z, yt))
        low.append((z, -yt))
    return up + low[-2:0:-1]


def pair(fn, x):
    return Geo().merge(fn(-x), fn(x))


def aggressive_aero():
    # Alerones: origen en el borde trasero del maletero, +z hacia delante (como spoiler_wing)
    r = part('spoiler_swan')        # cuello de cisne GT: el ala cuelga de dos brazos que la sujetan por arriba
    y0, z0, a = 0.46, -0.05, 0.14
    mesh(r, 'wing', prism(naca(0.36, 0.12), 1.62).rot('x', a).move(0, y0, z0), 'carbon', 0.004)
    mesh(r, 'gurney', box(1.62, 0.03, 0.006, (0, y0 + 0.18 * math.sin(a) + 0.015, z0 - 0.18 * math.cos(a))), 'carbon')
    plate = [(0.16, -0.05), (0.06, -0.07), (-0.21, -0.05), (-0.23, 0.07), (-0.06, 0.10), (0.13, 0.04)]
    mesh(r, 'endplates', pair(lambda x: prism(plate, 0.012, 'zy', (x, y0, z0)), 0.815), 'carbon', 0.003)
    neck = lambda x: sweep(rounded_poly([(x, 0.0, 0.18), (x, 0.34, 0.20), (x, 0.58, 0.10), (x, 0.58, -0.02), (x, 0.49, -0.05)], 0.07, 6),
                           rrect(0.06, 0.022, 0.008), up=(1.0, 0.0, 0.0))
    mesh(r, 'necks', pair(neck, 0.42), 'carbon', 0.003)
    mesh(r, 'feet', pair(lambda x: box(0.07, 0.012, 0.12, (x, 0.006, 0.18)), 0.42), 'dark', 0.003)

    r = part('spoiler_biplane')     # doble plano (time attack)
    mesh(r, 'main', prism(naca(0.32, 0.12), 1.56).rot('x', 0.10).move(0, 0.30, 0.02), 'carbon', 0.004)
    mesh(r, 'flap', prism(naca(0.18, 0.10), 1.56).rot('x', 0.42).move(0, 0.38, -0.16), 'carbon', 0.003)
    plate = [(0.17, -0.05), (0.17, 0.04), (-0.06, 0.13), (-0.25, 0.13), (-0.25, -0.03), (-0.04, -0.07)]
    mesh(r, 'endplates', pair(lambda x: prism(plate, 0.012, 'zy', (x, 0.30, 0.0)), 0.785), 'carbon', 0.003)
    mesh(r, 'uprights', pair(lambda x: prism([(0.08, 0.0), (-0.05, 0.0), (0.0, 0.30), (0.10, 0.30)], 0.025, 'zy', (x, 0, 0)), 0.40), 'carbon', 0.006)

    r = part('spoiler_tall')        # ala alta de rally sobre patas largas
    mesh(r, 'wing', prism(naca(0.28, 0.12), 1.48).rot('x', 0.08).move(0, 0.62, -0.02), 'carbon', 0.004)
    plate = [(0.15, -0.045), (0.15, 0.035), (-0.13, 0.06), (-0.15, -0.045)]
    mesh(r, 'endplates', pair(lambda x: prism(plate, 0.010, 'zy', (x, 0.62, -0.02)), 0.745), 'carbon', 0.003)
    mesh(r, 'legs', pair(lambda x: prism([(0.12, 0.0), (0.0, 0.0), (-0.06, 0.62), (0.06, 0.62)], 0.022, 'zy', (x, 0, 0)), 0.38), 'carbon', 0.005)

    r = part('spoiler_whale')       # cola de ballena con borde de goma
    tray = [(0.42, 0.0), (-0.04, 0.0), (-0.12, 0.07), (-0.14, 0.11), (0.28, 0.10)]
    mesh(r, 'tray', prism(tray, 1.50), 'paint', 0.02, 4)
    mesh(r, 'lip', box(1.52, 0.03, 0.03, (0, 0.105, -0.13)), 'rubber', 0.01)
    mesh(r, 'grille', box(0.90, 0.006, 0.18, (0, 0.102, 0.12)), 'dark', 0.003)

    r = part('spoiler_active')      # pala activa elevada con pistones
    blade = prism([(0.14, 0.0), (-0.12, 0.012), (-0.12, 0.030), (0.14, 0.018)], 1.56).rot('x', 0.22).move(0, 0.24, -0.04)
    mesh(r, 'blade', blade, 'paint', 0.006)
    mesh(r, 'rods', pair(lambda x: cyl(0.014, 0.22, 'y', (x, 0.12, 0.0)).rot('x', 0.18, (x, 0.0, 0.0)), 0.40), 'alu', 0.002)
    mesh(r, 'sleeves', pair(lambda x: cyl(0.024, 0.09, 'y', (x, 0.045, 0.0)).rot('x', 0.18, (x, 0.0, 0.0)), 0.40), 'dark', 0.003)
    mesh(r, 'bases', pair(lambda x: box(0.08, 0.012, 0.08, (x, 0.006, 0.0)), 0.40), 'dark', 0.003)

    # Difusores traseros: origen en la cara a ras del bajo, modelados hacia +z (la app los gira)
    r = part('diffuser_race')       # competición: aletas altas y luz de lluvia
    mesh(r, 'plate', box(1.70, 0.02, 0.44, (0, 0, -0.08)), 'carbon', 0.005)
    mesh(r, 'fins', Geo().merge(*[prism([(0.14, 0.0), (-0.30, 0.0), (-0.30, 0.02), (0.14, 0.17)], 0.012, 'zy', (k * 0.26, 0.01, 0)) for k in range(-3, 4)]), 'carbon', 0.002)
    mesh(r, 'rain_housing', box(0.12, 0.07, 0.03, (0, 0.12, 0.125)), 'dark', 0.004)
    mesh(r, 'rain_light', box(0.10, 0.05, 0.01, (0, 0.12, 0.142)), 'light', 0.002)

    r = part('diffuser_twin')       # doble túnel
    mesh(r, 'plate', box(1.60, 0.02, 0.36, (0, 0, -0.06)), 'carbon', 0.005)
    roofs = pair(lambda x: box(0.46, 0.012, 0.38).rot('x', -0.32).move(x, 0.075, -0.06), 0.45)
    mesh(r, 'tunnels', roofs, 'carbon', 0.003)
    mesh(r, 'walls', Geo().merge(*[prism([(0.12, 0.0), (-0.24, 0.0), (-0.24, 0.02), (0.12, 0.15)], 0.014, 'zy', (x, 0.01, 0)) for x in (-0.68, -0.22, 0.22, 0.68)]), 'carbon', 0.002)

    r = part('diffuser_blade')      # difusor con lama superior entre placas laterales
    mesh(r, 'plate', box(1.56, 0.02, 0.34, (0, 0, -0.06)), 'carbon', 0.005)
    mesh(r, 'fins', Geo().merge(*[prism([(0.10, 0.0), (-0.22, 0.0), (-0.22, 0.02), (0.10, 0.11)], 0.012, 'zy', (k * 0.30, 0.01, 0)) for k in range(-2, 3)]), 'carbon', 0.002)
    mesh(r, 'blade', prism(naca(0.16, 0.10), 1.56).rot('x', -0.15).move(0, 0.21, 0.05), 'carbon', 0.003)
    mesh(r, 'sides', pair(lambda x: prism([(0.15, 0.0), (-0.24, 0.0), (-0.24, 0.03), (0.15, 0.27)], 0.014, 'zy', (x, 0.0, 0)), 0.79), 'carbon', 0.003)

    # Delante: splitter de competición (origen a ras del bajo, +z hacia fuera) y canards dobles
    r = part('splitter_race')
    mesh(r, 'blade', prism([(-0.88, 0.0), (0.88, 0.0), (0.96, -0.18), (-0.96, -0.18)], 0.02, 'xz', (0, 0, 0.20)), 'carbon', 0.004)
    mesh(r, 'winglets', pair(lambda x: prism([(0.20, 0.0), (0.02, 0.0), (0.02, 0.10), (0.12, 0.10)], 0.012, 'zy', (x, 0.0, 0)), 0.95), 'carbon', 0.003)
    mesh(r, 'fins', Geo().merge(*[prism([(0.18, 0.0), (-0.02, 0.0), (-0.02, 0.05), (0.06, 0.05)], 0.012, 'zy', (x, 0.01, 0)) for x in (-0.6, -0.2, 0.2, 0.6)]), 'carbon', 0.002)

    r = part('canards_double')
    blades = Geo()
    for s_ in (-1, 1):
        for dy, k in ((0.07, 1.0), (0.17, 0.85)):
            blade = prism([(0.0, 0.0), (s_ * 0.20 * k, 0.0), (s_ * 0.15 * k, 0.12 * k), (0.0, 0.12 * k)], 0.012, 'xz')
            blades.merge(blade.rot('y', -s_ * 0.35).rot('z', s_ * 0.3).move(s_ * 0.80, dy, 0.0))
    mesh(r, 'blades', blades, 'carbon', 0.003)


# --------------------------------------------------------------------------- interiores
# Salpicaderos: origen en el centro del salpicadero, ancho de diseño 1.50 m (x), cara hacia el
# conductor en -z (el parabrisas queda hacia +z). El conductor va a la izquierda (x = -0.325).
# Las pantallas son caras con UV para que la app les ponga su imagen (mirando hacia -z)
SCREEN_UV = [(0, 0), (1, 0), (1, 1), (0, 1)]
XD = -0.325


def screen_quad(w, h, c, tilt=0.0):
    v = [(w / 2, -h / 2, 0.0), (-w / 2, -h / 2, 0.0), (-w / 2, h / 2, 0.0), (w / 2, h / 2, 0.0)]
    return Geo(v, [[0, 1, 2, 3]]).rot('x', tilt).move(*c)


def behind(c, tilt, d):
    """Punto d metros detrás de c (hacia +z) en una superficie inclinada tilt."""
    return (c[0], c[1] - d * math.sin(tilt), c[2] + d * math.cos(tilt))


def add_screen(r, name, w, h, c, tilt, role, frame=0.012, frame_role='dark'):
    mesh(r, name, screen_quad(w, h, c, tilt), role, keep_winding=True, uv=SCREEN_UV)
    mesh(r, name + '_frame', box(w + 2 * frame, h + 2 * frame, 0.014).rot('x', tilt).move(*behind(c, tilt, 0.0075)), frame_role, 0.004)


def ring_y(r_in, r_out, h, c):
    """Anillo plano con eje vertical."""
    return lathe([(r_in, 0.0), (r_out, 0.0), (r_out, h), (r_in, h)], 32).rot('x', -math.pi / 2).move(*c)


def ring_z(r_in, r_out, d, c):
    """Anillo con eje en z (mirando al conductor)."""
    return lathe([(r_in, -d / 2), (r_out, -d / 2), (r_out, d / 2), (r_in, d / 2)], 32).move(*c)


def round_vent(c):
    g = ring_z(0.038, 0.046, 0.014, c)
    blades = ring_of(lambda: box(0.036, 0.008, 0.004).rot('x', 0.5), 6, 0.018, 0.0).move(*c)
    return g, blades


def slat_vent(w, h, c, n=3):
    frame = Geo().merge(box(w, 0.006, 0.012, (c[0], c[1] + h / 2, c[2])), box(w, 0.006, 0.012, (c[0], c[1] - h / 2, c[2])),
                        box(0.006, h, 0.012, (c[0] - w / 2, c[1], c[2])), box(0.006, h, 0.012, (c[0] + w / 2, c[1], c[2])))
    slats = Geo().merge(*[box(w - 0.01, 0.004, 0.014, (c[0], c[1] - h / 2 + h * (k + 1) / (n + 1), c[2])).rot('x', 0.3, (c[0], c[1] - h / 2 + h * (k + 1) / (n + 1), c[2])) for k in range(n)])
    back = box(w, h, 0.004, (c[0], c[1], c[2] + 0.01))
    return frame, slats, back


def tweeter_top(c, rim='chrome'):
    """Altavoz de agudos en la parte superior del salpicadero (mirando hacia arriba)."""
    return ring_y(0.026, 0.032, 0.004, c), cyl(0.026, 0.004, 'y', (c[0], c[1] + 0.001, c[2]), 24)


def dash_common(r, profile, body_role, vents, glove_role='dash'):
    mesh(r, 'body', prism(profile, 1.50), body_role, 0.02, 4)
    # Guantera del acompañante con tirador
    mesh(r, 'glovebox', box(0.40, 0.11, 0.012, (0.33, -0.05, -0.172)), glove_role, 0.008)
    mesh(r, 'glovebox_handle', box(0.08, 0.012, 0.014, (0.33, -0.004, -0.182)), 'chrome', 0.003)
    # Equipo de sonido: tweeters en las esquinas y altavoz central encima
    for x in (-0.66, 0.66):
        ring, grille = tweeter_top((x, 0.088, 0.03))
        mesh(r, f'tweeter_ring_{x}', ring, 'chrome')
        mesh(r, f'tweeter_grille_{x}', grille, 'dark')
    mesh(r, 'center_speaker', box(0.22, 0.004, 0.06, (0, 0.098, -0.03)), 'dark', 0.002)
    mesh(r, 'center_speaker_rim', box(0.23, 0.003, 0.07, (0, 0.096, -0.03)), 'chrome', 0.002)
    # Mandos de climatización y botón de arranque
    mesh(r, 'climate', box(0.26, 0.05, 0.010, (0.02, -0.06, -0.176)), 'dark', 0.004)
    mesh(r, 'climate_knobs', Geo().merge(cyl(0.017, 0.022, 'z', (-0.075, -0.06, -0.188), 24), cyl(0.017, 0.022, 'z', (0.115, -0.06, -0.188), 24)), 'chrome', 0.003)
    mesh(r, 'climate_buttons', Geo().merge(*[box(0.022, 0.012, 0.006, (0.02 + k * 0.03, -0.06, -0.183)) for k in (-1, 0, 1)]), 'alu', 0.002)
    mesh(r, 'start_button', cyl(0.014, 0.012, 'z', (XD + 0.22, -0.03, -0.18), 24), 'red', 0.003)
    if vents == 'round':
        for x, y in ((-0.64, 0.0), (0.64, 0.0), (-0.12, 0.0), (0.16, 0.0)):
            g, b = round_vent((x, y, -0.178))
            mesh(r, f'vent_ring_{x}', g, 'chrome')
            mesh(r, f'vent_blades_{x}', b, 'dark')
    elif vents == 'slats':
        for x in (-0.64, 0.64, -0.17, 0.21):
            f, sl, bk = slat_vent(0.12, 0.05, (x, 0.0 if abs(x) > 0.5 else 0.065, -0.178))
            mesh(r, f'vent_frame_{x}', f, 'chrome')
            mesh(r, f'vent_slats_{x}', sl, 'chrome')
            mesh(r, f'vent_back_{x}', bk, 'dark')
    else:
        mesh(r, 'vent_slit', box(1.40, 0.008, 0.012, (0, 0.012, -0.170)), 'dark')


def dashboards():
    body = [(0.16, 0.06), (0.02, 0.10), (-0.10, 0.09), (-0.17, 0.04), (-0.17, -0.02), (-0.12, -0.10), (0.16, -0.10)]
    visor = [(-0.03, 0.0), (-0.19, 0.0), (-0.18, 0.02), (-0.03, 0.05)]

    r = part('dash_sport')
    dash_common(r, body, 'dash', 'round')
    mesh(r, 'carbon_band', box(1.40, 0.05, 0.010, (0, -0.012, -0.172)), 'carbon', 0.003)
    mesh(r, 'ambient', box(1.38, 0.005, 0.006, (0, -0.04, -0.176)), 'ambient')
    mesh(r, 'binnacle', prism(visor, 0.36, 'zy', (XD, 0.11, 0.0)), 'dash', 0.01)
    add_screen(r, 'cluster', 0.30, 0.10, (XD, 0.06, -0.16), 0.18, 'screen_cluster')
    add_screen(r, 'center', 0.22, 0.13, (0.02, 0.06, -0.178), 0.10, 'screen_info')

    r = part('dash_luxury')
    dash_common(r, body, 'dash', 'slats')
    mesh(r, 'top_pad', prism([(0.12, 0.085), (0.0, 0.112), (-0.10, 0.10), (-0.15, 0.07), (0.12, 0.07)], 1.48), 'leather', 0.015, 4)
    mesh(r, 'wood_band', box(1.40, 0.045, 0.012, (0, -0.005, -0.173)), 'wood', 0.004)
    mesh(r, 'chrome_line', box(1.40, 0.004, 0.006, (0, 0.022, -0.178)), 'chrome')
    mesh(r, 'binnacle', prism(visor, 0.36, 'zy', (XD, 0.11, 0.0)), 'leather', 0.012)
    add_screen(r, 'cluster', 0.30, 0.10, (XD, 0.06, -0.16), 0.18, 'screen_cluster', 0.012, 'chrome')
    add_screen(r, 'center', 0.26, 0.11, (0.02, 0.088, -0.160), 0.14, 'screen_info', 0.010, 'chrome')
    clock_c = (0.02, -0.012, -0.182)
    mesh(r, 'clock_ring', ring_z(0.027, 0.032, 0.012, clock_c), 'chrome')
    mesh(r, 'clock_face', cyl(0.027, 0.004, 'z', clock_c, 32), 'analog')
    mesh(r, 'clock_hands', Geo().merge(box(0.003, 0.021, 0.002, (0.02, -0.002, -0.186)), box(0.017, 0.003, 0.002, (0.028, -0.012, -0.186))), 'dark')

    r = part('dash_minimal')
    slim = [(0.16, 0.03), (-0.06, 0.05), (-0.16, 0.03), (-0.16, -0.03), (-0.10, -0.08), (0.16, -0.08)]
    dash_common(r, slim, 'dash', 'slit')
    mesh(r, 'ambient', box(1.38, 0.004, 0.006, (0, -0.006, -0.166)), 'ambient')
    add_screen(r, 'cluster', 0.24, 0.07, (XD, 0.085, -0.13), 0.20, 'screen_cluster')
    add_screen(r, 'center', 0.36, 0.21, (0.02, 0.17, -0.10), 0.14, 'screen_info', 0.010)
    mesh(r, 'tablet_stand', box(0.06, 0.10, 0.03, (0.02, 0.07, -0.07)), 'dark', 0.01)

    r = part('dash_futuristic')
    fut = [(0.16, 0.05), (0.0, 0.08), (-0.12, 0.075), (-0.18, 0.03), (-0.18, -0.03), (-0.10, -0.10), (0.16, -0.10)]
    dash_common(r, fut, 'dash', 'slit', 'carbon')
    mesh(r, 'ambient_top', box(1.40, 0.005, 0.006, (0, 0.035, -0.181)), 'ambient')
    mesh(r, 'ambient_low', box(1.40, 0.005, 0.006, (0, -0.085, -0.150)), 'ambient')
    add_screen(r, 'wide', 1.10, 0.11, (-0.12, 0.10, -0.135), 0.22, 'screen_wide', 0.010)


def steering_wheels():
    # Volantes: centro en el origen, aro en el plano xy mirando al conductor (-z); la columna sale hacia +z
    def column(r):
        mesh(r, 'column', cyl(0.034, 0.16, 'z', (0, -0.005, 0.10), 24, r2=0.046), 'dash', 0.006)
        mesh(r, 'stalks', Geo().merge(box(0.10, 0.012, 0.012, (-0.09, 0.0, 0.06)).rot('z', 0.15, (-0.04, 0.0, 0.06)),
                                      box(0.10, 0.012, 0.012, (0.09, 0.0, 0.06)).rot('z', -0.15, (0.04, 0.0, 0.06))), 'dark', 0.004)

    def rim_path(radius, flat=None, a0=0.0, a1=2 * math.pi, n=48):
        pts = []
        for k in range(n + 1):
            a = a0 + (a1 - a0) * k / n
            x, y = radius * math.cos(a), radius * math.sin(a)
            if flat is not None:
                y = max(y, flat)
            pts.append((x, y, 0.0))
        return pts

    r = part('steer_sport')         # deportivo de base plana con levas
    mesh(r, 'rim', tube(rim_path(0.175, flat=-0.148), 0.020, 12), 'leather', 0.0, 3, 50)
    mesh(r, 'marker', box(0.022, 0.03, 0.044, (0, 0.175, 0.0)), 'red', 0.004)
    mesh(r, 'spokes', Geo().merge(box(0.13, 0.03, 0.02, (-0.10, -0.01, 0.006)), box(0.13, 0.03, 0.02, (0.10, -0.01, 0.006)),
                                  box(0.03, 0.12, 0.02, (0, -0.095, 0.006))), 'carbon', 0.006)
    mesh(r, 'pad', box(0.12, 0.09, 0.035, (0, -0.005, 0.012)), 'leather', 0.016, 4)
    mesh(r, 'badge', cyl(0.015, 0.006, 'z', (0, 0.0, -0.007), 20), 'chrome')
    mesh(r, 'buttons', Geo().merge(*[box(0.016, 0.012, 0.006, (x, y, -0.006)) for x in (-0.11, -0.085, 0.085, 0.11) for y in (-0.002, -0.022)]), 'alu', 0.002)
    mesh(r, 'paddles', Geo().merge(box(0.035, 0.065, 0.005, (-0.115, 0.03, 0.045)), box(0.035, 0.065, 0.005, (0.115, 0.03, 0.045))), 'carbon', 0.003)
    column(r)

    r = part('steer_luxury')        # aro de madera arriba y cuero abajo
    mesh(r, 'rim_wood', tube(rim_path(0.185, a0=math.radians(35), a1=math.radians(145), n=20), 0.018, 12), 'wood', 0.0, 3, 50)
    mesh(r, 'rim_leather', tube(rim_path(0.185, a0=math.radians(145), a1=math.radians(395), n=40), 0.0185, 12), 'leather', 0.0, 3, 50)
    mesh(r, 'spokes', Geo().merge(*[box(0.12, 0.022, 0.016).move(0.11, 0, 0.006).rot('z', math.radians(a)) for a in (-15, 195, 250, 290)]), 'dash', 0.006)
    mesh(r, 'spoke_trim', Geo().merge(*[box(0.10, 0.004, 0.004).move(0.11, 0.012, -0.004).rot('z', math.radians(a)) for a in (-15, 195)]), 'chrome')
    mesh(r, 'pad', cyl(0.065, 0.035, 'z', (0, 0, 0.012), 32), 'leather', 0.012)
    mesh(r, 'pad_ring', ring_z(0.060, 0.068, 0.008, (0, 0, -0.006)), 'chrome')
    mesh(r, 'badge', cyl(0.018, 0.006, 'z', (0, 0, -0.008), 20), 'chrome')
    column(r)

    r = part('steer_minimal')       # aro fino de dos brazos
    mesh(r, 'rim', tube(rim_path(0.18), 0.016, 12), 'leather', 0.0, 3, 50)
    mesh(r, 'spokes', Geo().merge(box(0.14, 0.024, 0.016, (-0.10, 0.0, 0.006)), box(0.14, 0.024, 0.016, (0.10, 0.0, 0.006))), 'dash', 0.006)
    mesh(r, 'pad', cyl(0.05, 0.03, 'z', (0, 0, 0.01), 32), 'dash', 0.01)
    column(r)

    r = part('steer_yoke')          # yugo sin parte superior
    yoke = rounded_poly([(-0.17, 0.09, 0.0), (-0.17, -0.07, 0.0), (-0.12, -0.11, 0.0), (0.12, -0.11, 0.0), (0.17, -0.07, 0.0), (0.17, 0.09, 0.0)], 0.05, 6)
    mesh(r, 'rim', tube(yoke, 0.021, 12), 'leather', 0.0, 3, 50)
    mesh(r, 'grip_caps', Geo().merge(sphere(0.021, (-0.17, 0.09, 0.0), 12), sphere(0.021, (0.17, 0.09, 0.0), 12)), 'leather')
    mesh(r, 'spoke', box(0.32, 0.03, 0.02, (0, -0.01, 0.006)), 'carbon', 0.006)
    mesh(r, 'pad', box(0.20, 0.07, 0.03, (0, -0.01, 0.012)), 'dark', 0.012)
    mesh(r, 'pad_light', box(0.16, 0.004, 0.004, (0, 0.02, -0.004)), 'ambient')
    column(r)


def console_parts():
    # Origen en la superficie superior de la consola, +z hacia delante
    up = lambda g: g.rot('x', -math.pi / 2)     # lathe sobre z -> eje vertical
    r = part('shifter_manual')
    mesh(r, 'bezel', box(0.12, 0.008, 0.14, (0, 0.004, 0)), 'chrome', 0.004)
    mesh(r, 'boot', up(lathe([(0.0, 0.0), (0.055, 0.0), (0.045, 0.025), (0.022, 0.055), (0.012, 0.07), (0.0, 0.07)], 24, closed=False)), 'leather', 0.0, 3, 60)
    mesh(r, 'rod', cyl(0.008, 0.08, 'y', (0, 0.10, 0.0), 12), 'chrome')
    mesh(r, 'knob', sphere(0.028, (0, 0.155, 0.0), 16).scale(1, 1.15, 1).move(0, -0.023, 0), 'dash')
    mesh(r, 'knob_cap', cyl(0.018, 0.004, 'y', (0, 0.165, 0.0), 20), 'alu')

    r = part('shifter_auto')
    mesh(r, 'plate', box(0.10, 0.010, 0.20, (0, 0.005, 0)), 'carbon', 0.004)
    mesh(r, 'handle', box(0.04, 0.075, 0.10, (0, 0.045, -0.01)), 'leather', 0.015, 4)
    mesh(r, 'handle_top', box(0.036, 0.006, 0.07, (0, 0.084, -0.015)), 'chrome', 0.002)
    mesh(r, 'prnd', box(0.016, 0.003, 0.10, (0.035, 0.011, 0.0)), 'ambient')

    r = part('shifter_dial')
    mesh(r, 'base', box(0.11, 0.010, 0.11, (0, 0.005, 0)), 'dark', 0.004)
    mesh(r, 'dial', cyl(0.038, 0.032, 'y', (0, 0.026, 0), 32), 'alu', 0.004)
    mesh(r, 'dial_ring', ring_y(0.039, 0.043, 0.004, (0, 0.012, 0)), 'ambient')
    mesh(r, 'dial_grip', ring_of(lambda: box(0.004, 0.026, 0.006), 18, 0.038, 0.0).rot('x', -math.pi / 2).move(0, 0.027, 0), 'dark')

    r = part('console_top')         # portavasos, carga inalámbrica y mando giratorio (largo 0.40)
    mesh(r, 'plate', box(0.21, 0.006, 0.40, (0, 0.003, 0)), 'carbon', 0.003)
    for x in (-0.05, 0.05):
        mesh(r, f'cup_ring_{x}', ring_y(0.038, 0.044, 0.006, (x, 0.003, 0.12)), 'chrome')
        mesh(r, f'cup_well_{x}', cyl(0.038, 0.004, 'y', (x, 0.001, 0.12), 24), 'dark')
    mesh(r, 'charge_pad', box(0.10, 0.004, 0.14, (0, 0.007, -0.02)), 'dark', 0.002)
    mesh(r, 'charge_light', Geo().merge(box(0.10, 0.003, 0.004, (0, 0.008, 0.052)), box(0.10, 0.003, 0.004, (0, 0.008, -0.092))), 'ambient')
    mesh(r, 'knob', cyl(0.028, 0.024, 'y', (0, 0.018, -0.15), 32), 'alu', 0.003)
    mesh(r, 'knob_ring', ring_y(0.030, 0.036, 0.006, (0, 0.006, -0.15)), 'chrome')
    mesh(r, 'buttons', Geo().merge(*[box(0.022, 0.006, 0.014, (x, 0.008, z)) for x in (-0.07, 0.07) for z in (-0.13, -0.17)]), 'dark', 0.002)


def audio_parts():
    # Altavoces y piezas de puerta: origen en la superficie, mirando hacia +z (la app los gira)
    r = part('speaker_door')        # altavoz de graves con rejilla
    mesh(r, 'surround', ring_z(0.080, 0.095, 0.010, (0, 0, 0.005)), 'chrome')
    mesh(r, 'cone', lathe([(0.080, 0.002), (0.025, -0.022), (0.0, -0.022), (0.0, -0.024), (0.027, -0.024), (0.082, 0.0)], 32), 'dark')
    mesh(r, 'cap', sphere(0.022, (0, 0, -0.016), 16).scale(1, 1, 0.5), 'dark')
    mesh(r, 'grille', Geo().merge(*[ring_z(rr - 0.002, rr, 0.003, (0, 0, 0.011)) for rr in (0.02, 0.035, 0.05, 0.065, 0.08)]), 'alu')

    r = part('speaker_tweeter')
    mesh(r, 'ring', ring_z(0.022, 0.030, 0.008, (0, 0, 0.004)), 'chrome')
    mesh(r, 'dome', sphere(0.02, (0, 0, 0.0), 16).scale(1, 1, 0.5), 'alu')

    r = part('speaker_shelf')       # 6x9 de bandeja trasera, mirando hacia arriba (+y)
    oval = lambda rr, h, yc: cyl(rr, h, 'y', (0, yc, 0), 32).scale(1.5, 1, 1)
    mesh(r, 'frame', oval(0.075, 0.008, 0.004), 'dark', 0.002)
    mesh(r, 'grille', oval(0.066, 0.004, 0.009), 'alu')
    mesh(r, 'ring', ring_y(0.066, 0.075, 0.003, (0, 0.009, 0)).scale(1.5, 1, 1), 'chrome')

    r = part('door_handle_in')
    mesh(r, 'recess', box(0.11, 0.045, 0.012, (0, 0, 0.006)), 'dark', 0.006)
    mesh(r, 'lever', box(0.085, 0.012, 0.012, (0, 0.004, 0.018)), 'chrome', 0.004)

    r = part('door_switches')       # botonera de elevalunas sobre el reposabrazos (mirando hacia +y)
    mesh(r, 'pod', box(0.07, 0.016, 0.14, (0, 0.008, 0)), 'dark', 0.006)
    mesh(r, 'switches', Geo().merge(*[box(0.022, 0.008, 0.026, (x, 0.018, z)) for x in (-0.017, 0.017) for z in (-0.035, 0.0)]), 'alu', 0.003)
    mesh(r, 'trim', box(0.072, 0.004, 0.142, (0, 0.017, 0)).scale(1, 1, 1), 'chrome', 0.002)

    r = part('seat_screen')         # pantalla trasera en el reposacabezas, mirando hacia -z
    mesh(r, 'frame', box(0.23, 0.145, 0.016, (0, 0, -0.008)), 'dark', 0.006)
    mesh(r, 'screen', screen_quad(0.21, 0.125, (0, 0, -0.0165)), 'screen_rear', keep_winding=True, uv=SCREEN_UV)


# --------------------------------------------------------------------------- detalles exteriores
def exterior_details():
    # Discos de freno ventilados (radio de diseño 0.20, cara hacia +z, centrados en z = 0)
    for kind in ('plain', 'drilled', 'slotted'):
        r = part('brake_disc_' + kind)
        rotor = lathe([(0.11, -0.014), (0.20, -0.014), (0.20, 0.014), (0.11, 0.014)], 72)
        mesh(r, 'rotor', rotor, 'brake', 0.0, 3, 30)
        # ventilación entre las dos pistas (se ve por el canto)
        mesh(r, 'vanes', ring_of(lambda: box(0.085, 0.006, 0.010), 36, 0.155), 'dark')
        hat = lathe([(0.0, 0.032), (0.078, 0.032), (0.086, 0.024), (0.10, 0.012), (0.112, 0.006), (0.112, -0.008), (0.0, -0.008)], 48)
        mesh(r, 'hat', hat, 'steel', 0.0, 3, 30)
        mesh(r, 'nuts', ring_of(lambda: cyl(0.008, 0.012, 'z', (0, 0, 0.036), 6), 5, 0.05), 'chrome')
        if kind == 'drilled':
            holes = Geo()
            for ring_r, n, ph in ((0.13, 16, 0.0), (0.152, 16, 0.065), (0.175, 16, 0.13)):
                for k in range(n):
                    a = ph + 2 * math.pi * k / n
                    holes.merge(cyl(0.0055, 0.0295, 'z', (ring_r * math.cos(a), ring_r * math.sin(a), 0), 10))
            mesh(r, 'holes', holes, 'dark')
        if kind == 'slotted':
            mesh(r, 'slots', ring_of(lambda: box(0.07, 0.0045, 0.0295).rot('z', 0.55), 8, 0.155), 'dark')

    # Pinza de freno deportiva: bloque curvo que abraza el borde del disco (arriba, en +y)
    r = part('caliper_sport')
    arc = [(0.195 * math.sin(a), 0.195 * math.cos(a), 0.0) for a in [-0.55 + 1.1 * k / 12 for k in range(13)]]
    body = sweep(arc, rrect(0.075, 0.075, 0.012), up=(0.0, 0.0, 1.0))
    mesh(r, 'body', body, 'red', 0.004)
    mesh(r, 'bridge', sweep(arc[3:10], rrect(0.03, 0.08, 0.006), up=(0.0, 0.0, 1.0)).move(0, 0.03, 0), 'red', 0.003)
    mesh(r, 'pins', Geo().merge(cyl(0.007, 0.08, 'z', (-0.06, 0.215, 0), 12), cyl(0.007, 0.08, 'z', (0.06, 0.215, 0), 12)), 'chrome')
    r = part('caliper_classic')
    arc = [(0.19 * math.sin(a), 0.19 * math.cos(a), 0.0) for a in [-0.35 + 0.7 * k / 8 for k in range(9)]]
    mesh(r, 'body', sweep(arc, rrect(0.055, 0.07, 0.01), up=(0.0, 0.0, 1.0)), 'red', 0.004)

    # Limpiaparabrisas en reposo: pivote en el origen, brazo y escobilla hacia -x (largo total 1),
    # y = 0 es la superficie del cristal y z sube por el cristal
    r = part('wiper')
    mesh(r, 'pivot', cyl(0.022, 0.026, 'y', (0, 0.013, 0), 20), 'plastic', 0.004)
    mesh(r, 'arm', sweep([(-0.01, 0.026, 0.0), (-0.12, 0.022, 0.004), (-0.55, 0.018, 0.012), (-0.86, 0.016, 0.016)], rrect(0.016, 0.008, 0.003), up=(0.0, 1.0, 0.0)), 'plastic')
    mesh(r, 'blade', box(0.80, 0.012, 0.016, (-0.56, 0.009, 0.024)), 'plastic', 0.003)
    mesh(r, 'rubber', box(0.80, 0.004, 0.006, (-0.56, 0.002, 0.024)), 'rubber')
    mesh(r, 'spoiler', box(0.42, 0.006, 0.014, (-0.62, 0.018, 0.020)).rot('x', -0.5, (-0.62, 0.018, 0.020)), 'plastic')

    # Rejilla de la base del parabrisas (ancho 1, fondo 0.11, cara hacia +y)
    r = part('cowl')
    mesh(r, 'panel', box(1.0, 0.008, 0.11, (0, 0.004, 0)), 'plastic', 0.003)
    slots = Geo()
    for k in range(18):
        x = -0.40 + 0.80 * k / 17
        slots.merge(box(0.028, 0.004, 0.05, (x, 0.008, 0.012)))
    mesh(r, 'slots', slots, 'dark')

    # Tapa de depósito / carga (cara hacia +z, enrasada en z = 0)
    r = part('fuel_door')
    mesh(r, 'door', prism(rrect(0.17, 0.12, 0.025, 5), 0.004, 'xy', (0, 0, 0.002)), 'paint', 0.0015)
    mesh(r, 'gap', prism(rrect(0.18, 0.13, 0.03, 5), 0.002, 'xy', (0, 0, 0.0005)), 'dark')
    r = part('fuel_door_round')
    mesh(r, 'door', cyl(0.062, 0.004, 'z', (0, 0, 0.002), 40), 'paint', 0.0015)
    mesh(r, 'gap', cyl(0.067, 0.002, 'z', (0, 0, 0.0005), 40), 'dark')

    # Tercera luz de freno (cara hacia +z): carcasa oscura y franja de luz
    r = part('chmsl')
    mesh(r, 'housing', box(0.26, 0.032, 0.03, (0, 0, -0.012)), 'plastic', 0.004)
    mesh(r, 'light', box(0.23, 0.012, 0.006, (0, 0, 0.004)), 'light_red')


# --------------------------------------------------------------------------- parrilla paramétrica
def parametric_grille():
    """Parrilla de facetas tipo joya con las luces diurnas escondidas en sus extremos (estilo
    Tucson). Medidas de diseño: 1.50 de ancho arriba, 1.04 abajo y 0.40 de alto, centrada en el
    origen y con la cara hacia +z (la app la escala al hueco de la parrilla)."""
    r = part('grille_parametric')
    top, bot, half_top, half_bot = 0.20, -0.20, 0.75, 0.52

    def xm(y):   # medio ancho del trapecio a la altura y
        return half_bot + (y - bot) / (top - bot) * (half_top - half_bot)

    # Fondo oscuro con las esquinas achaflanadas
    ch = 0.03
    outline = [(-half_top + ch, top), (half_top - ch, top), (half_top, top - ch), (half_bot, bot + ch),
               (half_bot - ch, bot), (-half_bot + ch, bot), (-half_bot, bot + ch), (-half_top, top - ch)]
    mesh(r, 'base', prism(outline, 0.05, 'xy', (0, 0, -0.03)), 'dark')

    # Sección facetada (u en el plano de la parrilla, v hacia fuera): dos caras en punta que brillan
    jewel = [(-0.009, -0.035), (-0.009, 0.0), (0.0, 0.011), (0.009, 0.0), (0.009, -0.035)]
    blade = [(-0.0065, -0.03), (-0.0065, 0.004), (0.0065, 0.004), (0.0065, -0.03)]
    up = (0.0, 0.0, 1.0)

    # Cada fila es horizontal en el centro y se abre en ala hacia los lados (más abajo cuanto más
    # baja es la fila); en las cuatro de arriba el tramo exterior es la lama de luz diurna
    rows = [0.160, 0.085, 0.010, -0.065, -0.140]

    def row_y(ri, x):
        y = rows[ri]
        span = max(0.2, xm(y) - 0.16)
        u = max(0.0, (abs(x) - 0.16) / span)
        return y - (0.014 + 0.040 * ri) * u ** 1.5

    def row_pts(ri, x0, x1, n):
        return [(x0 + (x1 - x0) * i / n, row_y(ri, x0 + (x1 - x0) * i / n), 0.0) for i in range(n + 1)]

    bars, links, drl = Geo(), Geo(), Geo()
    lim = []
    for ri, y in enumerate(rows):
        edge = xm(y) - 0.02
        inner = 0.47 if ri <= 3 else edge
        lim.append(inner)
        bars.merge(sweep(row_pts(ri, -inner, inner, 40), jewel, up=up))
        if ri <= 3:
            for sgn in (-1, 1):
                pts = row_pts(ri, sgn * 0.485, sgn * (edge + 0.03), 8)
                drl.merge(sweep(pts if sgn > 0 else pts[::-1], blade, up=up))
    # Entre cada dos filas, diagonales en zigzag: triángulos facetados (celdas de joya), que se
    # abren hacia los lados como las filas
    for ri in range(len(rows) - 1):
        top_lim = min(lim[ri], lim[ri + 1]) - 0.02
        step = 0.075
        k0 = 0 if ri % 2 == 0 else 1
        n = int(top_lim / step)
        for sgn in (-1, 1):
            pts = []
            for k in range(0, n + 1):
                x = sgn * k * step
                upper = (k + k0) % 2 == 0
                pts.append((x, row_y(ri, x) - 0.004 if upper else row_y(ri + 1, x) + 0.004, 0.0))
            for a, b in zip(pts[:-1], pts[1:]):
                xm_ab = (a[0] + b[0]) / 2
                if abs(xm_ab) < 0.11 and ri in (1, 2):
                    continue   # hueco para el emblema
                links.merge(sweep([a, b], jewel, up=up))
    mesh(r, 'jewels', bars, 'darkchrome', 0.0, 3, 25)
    mesh(r, 'links', links, 'darkchrome', 0.0, 3, 25)
    mesh(r, 'drl', drl, 'light', 0.0, 3, 25)

    # Emblema ovalado genérico en el centro
    ell = [(0.085 * math.cos(2 * math.pi * k / 40), 0.012 + 0.052 * math.sin(2 * math.pi * k / 40)) for k in range(40)]
    mesh(r, 'badge_fill', prism(ell, 0.012, 'xy', (0, 0, 0.012)), 'dark')
    ring_path = [(px, py, 0.019) for px, py in ell] + [(ell[0][0], ell[0][1], 0.019)]
    mesh(r, 'badge_ring', tube(ring_path, 0.006, 10), 'chrome')
    mesh(r, 'badge_mark', prism([(-0.05, -0.012), (0.05, 0.036), (0.05, 0.026), (-0.05, -0.022)], 0.006, 'xy', (0, 0.012, 0.02)), 'chrome')


# --------------------------------------------------------------------------- zaga estilo Tucson
def suv_rear_parts():
    # Piloto en garras (lado derecho, x hacia fuera, cara hacia +z): fondo oscuro, tres cuchillas
    # inclinadas y una tira fina arriba que se une a la barra de lado a lado
    r = part('tail_claw')
    back = [(-0.16, 0.03), (0.16, 0.03), (0.16, -0.05), (0.07, -0.13), (-0.10, -0.13)]
    mesh(r, 'back', prism(back, 0.02, 'xy', (0, 0, -0.008)), 'dark', 0.002)
    mesh(r, 'topline', box(0.32, 0.012, 0.02, (0, 0.022, 0.006)), 'light_red', 0.002)
    blades = Geo()
    for k, (x0, h) in enumerate([(-0.07, 0.115), (-0.005, 0.10), (0.06, 0.08)]):
        # paralelogramo: arriba desplazado hacia fuera, como una garra
        pts = [(x0, -0.015), (x0 + 0.026, -0.015), (x0 - 0.035, -0.015 - h), (x0 - 0.061, -0.015 - h)]
        blades.merge(prism(pts, 0.016, 'xy', (0, 0, 0.006)))
    mesh(r, 'blades', blades, 'light_red', 0.002)
    mesh(r, 'rim', prism([(0.16, 0.03), (0.17, 0.03), (0.17, -0.055), (0.075, -0.14), (0.065, -0.13), (0.16, -0.05)], 0.018, 'xy', (0, 0, -0.004)), 'darkchrome')

    # Alerón de techo grande: prolonga el techo sobre la luneta cayendo un poco, con dos aletas
    # negras que bajan por los lados del cristal y la tercera luz de freno bajo el borde
    # (ancho de diseño 1.40, como spoiler_roof)
    r = part('spoiler_roofwing')
    body = [(0.08, 0.0), (-0.20, -0.030), (-0.235, -0.026), (-0.235, -0.006), (-0.20, 0.004), (0.08, 0.030)]
    mesh(r, 'body', prism(body, 1.40), 'roof', 0.008)
    # Labio oscuro bajo el borde de salida (separa el alerón de la luneta)
    mesh(r, 'lip', prism([(-0.10, -0.022), (-0.225, -0.034), (-0.225, -0.026), (-0.10, -0.014)], 1.30), 'dark', 0.002)
    fins = Geo()
    for x in (-0.68, 0.68):
        fins.merge(prism([(-0.04, -0.035), (-0.20, -0.075), (-0.22, -0.028), (0.02, 0.0)], 0.026, 'zy', (x, 0, 0)))
    mesh(r, 'fins', fins, 'dark', 0.004)
    mesh(r, 'chmsl', box(0.56, 0.006, 0.012, (0, -0.031, -0.205)), 'light_red', 0.002)

    # Protector plateado trasero (cara hacia +z, la app lo gira): banda en U, difusor oscuro con
    # aletas, dos salidas de escape trapezoidales y catadióptricos rojos en las puntas
    r = part('skid_rear')
    band = [(-0.76, 0.13), (-0.68, 0.13), (-0.58, 0.035), (0.58, 0.035), (0.68, 0.13), (0.76, 0.13), (0.70, -0.035), (-0.70, -0.035)]
    mesh(r, 'band', prism(band, 0.028, 'xy'), 'alu', 0.004)
    mesh(r, 'diffuser', prism([(-0.52, 0.03), (0.52, 0.03), (0.46, -0.03), (-0.46, -0.03)], 0.02, 'xy', (0, 0, 0.012)), 'dark', 0.002)
    vanes = Geo()
    for x in (-0.18, -0.06, 0.06, 0.18):
        vanes.merge(box(0.008, 0.05, 0.02, (x, 0.0, 0.02)))
    mesh(r, 'vanes', vanes, 'darkchrome')
    pipes, rims = Geo(), Geo()
    for x in (-0.36, 0.36):
        trap = [(x - 0.07, 0.025), (x + 0.07, 0.025), (x + 0.055, -0.02), (x - 0.055, -0.02)]
        pipes.merge(prism(trap, 0.03, 'xy', (0, 0, 0.012)))
        outer = [(x - 0.08, 0.032), (x + 0.08, 0.032), (x + 0.063, -0.027), (x - 0.063, -0.027)]
        rims.merge(prism(outer, 0.024, 'xy', (0, 0, 0.012)))
    mesh(r, 'tips', rims, 'chrome', 0.002)
    mesh(r, 'pipes', pipes, 'dark')
    refl = Geo()
    for sgn in (-1, 1):
        refl.merge(prism([(sgn * 0.70, 0.09), (sgn * 0.745, 0.125), (sgn * 0.745, 0.14), (sgn * 0.70, 0.105)], 0.034, 'xy', (0, 0, 0.004)))
    mesh(r, 'reflectors', refl, 'reflector', 0.002)

    # Protector plateado delantero: la misma banda con una lámina central
    r = part('skid_front')
    mesh(r, 'band', prism(band, 0.028, 'xy'), 'alu', 0.004)
    mesh(r, 'lip', prism([(-0.40, 0.03), (0.40, 0.03), (0.34, -0.03), (-0.34, -0.03)], 0.03, 'xy', (0, 0, 0.012)), 'alu', 0.004)
    mesh(r, 'lipline', box(0.70, 0.008, 0.03, (0, 0.0, 0.016)), 'dark')


# --------------------------------------------------------------------------- frontal y zaga bajos
def lower_fascia_parts():
    # ---- Molduras bajo la parrilla: ancho de diseño 1.0, origen en el centro sobre la chapa
    r = part('trim_bar')            # lama cromada recta
    mesh(r, 'bar', sweep([(-0.5 + k / 10, 0.0, 0.004) for k in range(11)], rrect(0.012, 0.016, 0.005)), 'chrome', 0.003)

    r = part('trim_smile')          # sonrisa cromada: sube en los extremos
    pts = [(x, 0.075 * abs(2 * x) ** 3, 0.004) for x in [-0.5 + k / 40 for k in range(41)]]
    mesh(r, 'bar', sweep(pts, rrect(0.012, 0.015, 0.005)), 'chrome', 0.003)

    r = part('trim_wing')           # ala de aluminio con los extremos hacia abajo
    pts = rounded_poly([(-0.5, -0.11, 0.004), (-0.41, 0.0, 0.004), (0.41, 0.0, 0.004), (0.5, -0.11, 0.004)], 0.05, 6)
    mesh(r, 'blade', sweep(pts, [(-0.004, -0.016), (0.016, -0.011), (0.016, 0.011), (-0.004, 0.016)]), 'alu', 0.003)
    mesh(r, 'shadow', sweep([(p[0], p[1] - 0.024, 0.0) for p in pts], rrect(0.008, 0.010, 0.003)), 'gloss')

    r = part('trim_gloss')          # banda negra brillante con filo cromado
    mesh(r, 'band', box(1.0, 0.040, 0.010, (0, 0, 0.002)), 'gloss', 0.003)
    mesh(r, 'edge', box(1.0, 0.006, 0.006, (0, 0.021, 0.006)), 'chrome', 0.0015)

    r = part('trim_led')            # tira de luz diurna bajo la parrilla
    mesh(r, 'channel', box(1.02, 0.024, 0.010, (0, 0, 0.0)), 'dark', 0.003)
    mesh(r, 'led', box(1.0, 0.010, 0.006, (0, 0, 0.004)), 'light', 0.002)

    # ---- Faldones delanteros decorativos (ancho de diseño 1.90, origen en el borde inferior)
    r = part('apron_lip_alu')       # labio de aluminio que sube en las esquinas
    pts = rounded_poly([(-0.92, 0.12, 0.0), (-0.78, 0.0, 0.0), (0.78, 0.0, 0.0), (0.92, 0.12, 0.0)], 0.07, 6)
    mesh(r, 'lip', sweep(pts, [(-0.008, -0.004), (0.045, -0.004), (0.05, 0.002), (0.012, 0.026), (-0.008, 0.026)]), 'alu', 0.003)

    r = part('apron_black')         # faldón negro texturizado con rejilla central y lamas plateadas
    band = [(-0.93, 0.0), (0.93, 0.0), (0.95, 0.17), (0.80, 0.17), (0.66, 0.095), (-0.66, 0.095), (-0.80, 0.17), (-0.95, 0.17)]
    mesh(r, 'band', prism(band, 0.024, 'xy', (0, 0, 0.0)), 'textured', 0.004)
    mesh(r, 'insert', box(1.0, 0.052, 0.010, (0, 0.046, 0.011)), 'dark', 0.003)
    mesh(r, 'slats', Geo().merge(box(0.98, 0.006, 0.012, (0, 0.034, 0.014)), box(0.98, 0.006, 0.012, (0, 0.058, 0.014))), 'alu')
    mesh(r, 'underlip', box(1.20, 0.012, 0.04, (0, 0.006, 0.02)), 'alu', 0.004)

    r = part('apron_wing')          # ala cromada que enmarca las tomas laterales y labio negro
    pts = rounded_poly([(-0.88, 0.25, 0.008), (-0.80, 0.05, 0.008), (0.80, 0.05, 0.008), (0.88, 0.25, 0.008)], 0.06, 6)
    mesh(r, 'wing', sweep(pts, rrect(0.012, 0.022, 0.005)), 'chrome', 0.003)
    mesh(r, 'lip', prism([(-0.80, -0.005), (0.80, -0.005), (0.74, 0.05), (-0.74, 0.05)], 0.014, 'xz', (0, 0.007, 0)), 'gloss', 0.004)

    r = part('apron_splitter')      # splitter negro brillante de tres piezas con placas
    mesh(r, 'blade', prism([(-0.86, -0.01), (0.86, -0.01), (0.80, 0.075), (-0.80, 0.075)], 0.014, 'xz', (0, 0.007, 0)), 'gloss', 0.004)
    mesh(r, 'face', box(1.60, 0.05, 0.012, (0, 0.035, 0.0)), 'gloss', 0.003)
    mesh(r, 'line', box(0.90, 0.008, 0.010, (0, 0.035, 0.008)), 'alu')
    plates = Geo()
    for x in (-0.84, 0.84):
        plates.merge(prism([(-0.01, 0.0), (0.075, 0.0), (0.045, 0.075), (-0.01, 0.075)], 0.012, 'zy', (x, 0, 0)))
    mesh(r, 'plates', plates, 'gloss', 0.003)

    r = part('apron_guard')         # protector negro de campo con placa plateada y ganchos
    guard = [(-0.94, 0.0), (0.94, 0.0), (0.94, 0.12), (0.70, 0.15), (-0.70, 0.15), (-0.94, 0.12)]
    mesh(r, 'band', prism(guard, 0.03, 'xy'), 'textured', 0.005)
    mesh(r, 'plate', prism([(-0.42, 0.0), (0.42, 0.0), (0.36, 0.095), (-0.36, 0.095)], 0.02, 'xy', (0, 0, 0.02)), 'alu', 0.004)
    mesh(r, 'bolts', Geo().merge(*[cyl(0.008, 0.006, 'z', (x, 0.07, 0.031), 10) for x in (-0.30, -0.10, 0.10, 0.30)]), 'steel')
    hooks = Geo()
    for x in (-0.58, 0.58):
        hooks.merge(tube([(x + 0.03 * math.cos(math.pi * k / 10), 0.06 + 0.03 * math.sin(math.pi * k / 10), 0.035) for k in range(11)], 0.008, 10))
        hooks.merge(box(0.075, 0.016, 0.02, (x, 0.06, 0.022)))
    mesh(r, 'hooks', hooks, 'red')

    # ---- Faldones traseros decorativos (modelados hacia +z; la app los gira)
    r = part('rapron_black')        # negro con aletas de difusor y catadióptricos
    mesh(r, 'band', prism(band, 0.024, 'xy'), 'textured', 0.004)
    fins = Geo()
    for x in (-0.36, -0.18, 0.0, 0.18, 0.36):
        fins.merge(prism([(0.0, 0.0), (0.05, 0.0), (0.02, 0.07), (0.0, 0.07)], 0.010, 'zy', (x, 0, 0.004)))
    mesh(r, 'fins', fins, 'dark')
    mesh(r, 'reflectors', Geo().merge(box(0.03, 0.10, 0.012, (-0.86, 0.11, 0.014)), box(0.03, 0.10, 0.012, (0.86, 0.11, 0.014))), 'reflector', 0.003)

    r = part('rapron_chrome')       # banda negra brillante con lama cromada y catadióptricos
    mesh(r, 'band', prism([(-0.90, 0.0), (0.90, 0.0), (0.92, 0.09), (-0.92, 0.09)], 0.02, 'xy'), 'gloss', 0.004)
    mesh(r, 'strip', box(1.40, 0.014, 0.010, (0, 0.125, 0.006)), 'chrome', 0.003)
    mesh(r, 'reflectors', Geo().merge(box(0.16, 0.022, 0.010, (-0.82, 0.125, 0.006)), box(0.16, 0.022, 0.010, (0.82, 0.125, 0.006))), 'reflector', 0.003)

    r = part('rapron_valance')      # negro brillante con marcos cromados de escape trapezoidales
    mesh(r, 'band', prism([(-0.92, 0.0), (0.92, 0.0), (0.92, 0.14), (-0.92, 0.14)], 0.02, 'xy'), 'gloss', 0.004)
    frames, holes = Geo(), Geo()
    for x in (-0.48, 0.48):
        frames.merge(prism([(x - 0.14, 0.11), (x + 0.14, 0.11), (x + 0.12, 0.03), (x - 0.12, 0.03)], 0.02, 'xy', (0, 0, 0.008)))
        holes.merge(prism([(x - 0.125, 0.10), (x + 0.125, 0.10), (x + 0.107, 0.04), (x - 0.107, 0.04)], 0.02, 'xy', (0, 0, 0.011)))
    mesh(r, 'frames', frames, 'chrome', 0.003)
    mesh(r, 'holes', holes, 'dark')
    mesh(r, 'line', box(0.68, 0.008, 0.008, (0, 0.10, 0.014)), 'chrome')

    r = part('rapron_guard')        # protector negro con placa plateada y gancho
    mesh(r, 'band', prism(guard, 0.03, 'xy'), 'textured', 0.005)
    mesh(r, 'plate', prism([(-0.40, 0.0), (0.40, 0.0), (0.34, 0.09), (-0.34, 0.09)], 0.02, 'xy', (0, 0, 0.02)), 'alu', 0.004)
    mesh(r, 'hook', tube([(0.58 + 0.03 * math.cos(math.pi * k / 10), 0.06 + 0.03 * math.sin(math.pi * k / 10), 0.035) for k in range(11)], 0.008, 10), 'red')

    r = part('rapron_lip')          # labio de aluminio trasero
    pts = rounded_poly([(-0.92, 0.10, 0.0), (-0.80, 0.0, 0.0), (0.80, 0.0, 0.0), (0.92, 0.10, 0.0)], 0.06, 6)
    mesh(r, 'lip', sweep(pts, [(-0.008, -0.004), (0.03, -0.004), (0.035, 0.002), (0.010, 0.024), (-0.008, 0.024)]), 'alu', 0.003)

    # ---- Luces bajas delanteras (segundo nivel): lado derecho, +x hacia fuera, cara hacia +z
    r = part('fog_cube')            # tres cubos LED
    mesh(r, 'housing', box(0.17, 0.052, 0.04, (0, 0, -0.012)), 'dark', 0.008)
    mesh(r, 'cubes', Geo().merge(*[box(0.034, 0.030, 0.02, (x, 0, 0.006)) for x in (-0.05, 0.0, 0.05)]), 'light', 0.003)

    r = part('fog_vertical')        # tira LED vertical con filo cromado
    mesh(r, 'housing', box(0.042, 0.17, 0.035, (0, 0, -0.01)), 'dark', 0.008)
    mesh(r, 'led', box(0.016, 0.15, 0.02, (0, 0, 0.004)), 'light', 0.004)
    mesh(r, 'edge', box(0.004, 0.17, 0.02, (0.023, 0, 0.002)), 'chrome')

    r = part('fog_cluster')         # faro principal en el paragolpes: dos proyectores e intermitente
    mesh(r, 'housing', prism(rrect(0.23, 0.10, 0.03), 0.05, 'xy', (0, 0, -0.016)), 'dark', 0.004)
    proj, rings = Geo(), Geo()
    for x in (-0.065, 0.005):
        proj.merge(cyl(0.025, 0.012, 'z', (x, 0, 0.004), 24))
        rings.merge(lathe([(0.026, -0.004), (0.034, -0.004), (0.034, 0.006), (0.027, 0.008)], 28).move(x, 0, 0.0))
    mesh(r, 'projectors', proj, 'light')
    mesh(r, 'rings', rings, 'chrome')
    mesh(r, 'amber', box(0.028, 0.068, 0.012, (0.083, 0, 0.002)), 'amber', 0.003)

    r = part('fog_triangle')        # triángulo con contorno LED que apunta hacia dentro
    tri = [(0.085, 0.04), (-0.085, 0.04), (0.085, -0.045)]
    mesh(r, 'housing', prism(tri, 0.04, 'xy', (0, 0, -0.012)), 'dark', 0.004)
    edge = [(0.075, 0.032, 0.006), (-0.06, 0.032, 0.006), (0.075, -0.032, 0.006), (0.075, 0.032, 0.006)]
    mesh(r, 'led', sweep(edge, rrect(0.008, 0.008, 0.003), up=(0.0, 0.0, 1.0)), 'light')

    # ---- Luces bajas traseras: en el paragolpes, lado derecho mirando hacia +z
    r = part('rlow_reflector')      # catadióptrico vertical
    mesh(r, 'reflector', box(0.03, 0.12, 0.012), 'reflector', 0.004)

    r = part('rlow_vertical')       # tira LED roja vertical
    mesh(r, 'housing', box(0.042, 0.17, 0.035, (0, 0, -0.01)), 'dark', 0.008)
    mesh(r, 'led', box(0.016, 0.15, 0.02, (0, 0, 0.004)), 'light_red', 0.004)

    r = part('rlow_round')          # antiniebla rojo y luz de marcha atrás
    mesh(r, 'housing', prism(rrect(0.17, 0.07, 0.034), 0.04, 'xy', (0, 0, -0.014)), 'dark', 0.004)
    mesh(r, 'fog', cyl(0.026, 0.012, 'z', (0.042, 0, 0.004), 24), 'light_red')
    mesh(r, 'reverse', cyl(0.026, 0.012, 'z', (-0.042, 0, 0.004), 24), 'lens')
    mesh(r, 'reflector', cyl(0.024, 0.004, 'z', (-0.042, 0, -0.003), 24), 'chrome')

    r = part('rlow_cluster')        # segundo piloto: L roja, marcha atrás e intermitente
    mesh(r, 'housing', prism(rrect(0.24, 0.09, 0.025), 0.045, 'xy', (0, 0, -0.016)), 'dark', 0.004)
    mesh(r, 'red', Geo().merge(box(0.21, 0.014, 0.014, (0.0, 0.030, 0.004)), box(0.014, 0.07, 0.014, (0.105, 0.0, 0.004))), 'light_red', 0.003)
    mesh(r, 'reverse', box(0.10, 0.034, 0.012, (-0.035, -0.010, 0.002)), 'lens', 0.004)
    mesh(r, 'reflector', box(0.098, 0.032, 0.004, (-0.035, -0.010, -0.006)), 'chrome')
    mesh(r, 'amber', box(0.05, 0.034, 0.012, (0.055, -0.010, 0.002)), 'amber', 0.004)

    r = part('rlow_bar')            # barra roja fina de lado a lado (ancho de diseño 1.0)
    mesh(r, 'channel', box(1.02, 0.024, 0.010, (0, 0, 0.0)), 'dark', 0.003)
    mesh(r, 'led', box(1.0, 0.010, 0.006, (0, 0, 0.004)), 'light_red', 0.002)

    # ---- Relleno de las tomas de aire (cara hacia +z, origen en el centro del frente)
    r = part('insert_blade')        # lama horizontal de perfil alar de 1.0 de ancho
    mesh(r, 'blade', sweep([(-0.5 + k / 10, 0.0, 0.0) for k in range(11)], [(-0.03, -0.006), (0.012, -0.010), (0.016, 0.0), (0.012, 0.010), (-0.03, 0.006)]), 'alu', 0.002)


def main():
    global MATS
    MATS = reset_scene()
    seat_front()
    seat_rear()
    mirrors()
    handles()
    spoilers()
    bumpers()
    exhausts()
    small_parts()
    new_parts()
    lamp_parts()
    hubcaps()
    aggressive_aero()
    dashboards()
    steering_wheels()
    console_parts()
    audio_parts()
    exterior_details()
    parametric_grille()
    suv_rear_parts()
    lower_fascia_parts()
    bpy.ops.export_scene.gltf(
        filepath=OUT, export_format='GLB', export_apply=True, export_yup=True,
        export_cameras=False, export_lights=False, export_extras=False, export_texcoords=True,
    )
    print(f'PARTS {len([o for o in bpy.data.objects if o.type == "EMPTY"])} meshes {len([o for o in bpy.data.objects if o.type == "MESH"])} -> {OUT}')


main()

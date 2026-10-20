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
    bpy.ops.export_scene.gltf(
        filepath=OUT, export_format='GLB', export_apply=True, export_yup=True,
        export_cameras=False, export_lights=False, export_extras=False, export_texcoords=True,
    )
    print(f'PARTS {len([o for o in bpy.data.objects if o.type == "EMPTY"])} meshes {len([o for o in bpy.data.objects if o.type == "MESH"])} -> {OUT}')


main()

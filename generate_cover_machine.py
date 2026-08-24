#!/usr/bin/env python3
r"""Generate the thesis cover image: an abstract machine of the find2fix pipeline.

Emits a single-page vector PDF (no external dependencies) with the same page
size as the previous cover (maze.pdf, 603x378pt) so that
\coverpicture{\includegraphics[width=13cm]{img/machine.pdf}} keeps the layout.

Pipeline read left to right:
  buggy program -> funnel -> fault-localisation grader (ranked suspicious spots)
  the same source -> template mill (gears) -> grammar drum
  -> synthesis core (search tree, one path found)
  -> test-suite gates (rejects loop back) -> tray with the patched program
"""
import math
import os

W, H = 603.0, 378.0

# ---------------------------------------------------------------- pdf writer
class Canvas:
    def __init__(self):
        self.ops = []

    def _f(self, *vals):
        return " ".join(("%.3f" % v).rstrip("0").rstrip(".") or "0" for v in vals)

    # --- graphics state
    def gs(self, lw=None, gray=None, dash=None, cap=1, join=1):
        self.ops.append("q")
        self.ops.append("%d J %d j" % (cap, join))
        if lw is not None:
            self.ops.append("%s w" % self._f(lw))
        if gray is not None:
            self.ops.append("%s G" % self._f(gray))
            self.ops.append("%s g" % self._f(gray))
        if dash:
            self.ops.append("[%s] 0 d" % " ".join(self._f(d) for d in dash))
        return self

    def grestore(self):
        self.ops.append("Q")

    # --- path primitives
    def moveto(self, x, y):
        self.ops.append("%s m" % self._f(x, y))

    def lineto(self, x, y):
        self.ops.append("%s l" % self._f(x, y))

    def curveto(self, x1, y1, x2, y2, x3, y3):
        self.ops.append("%s c" % self._f(x1, y1, x2, y2, x3, y3))

    def close(self):
        self.ops.append("h")

    def stroke(self):
        self.ops.append("S")

    def fill(self):
        self.ops.append("f")

    def fillstroke(self):
        self.ops.append("B")

    # --- shapes
    def line(self, x0, y0, x1, y1):
        self.moveto(x0, y0)
        self.lineto(x1, y1)
        self.stroke()

    def polyline(self, pts, closed=False, mode="S"):
        self.moveto(*pts[0])
        for p in pts[1:]:
            self.lineto(*p)
        if closed:
            self.close()
        self.ops.append(mode)

    def circle_path(self, cx, cy, r):
        k = 0.5522847498 * r
        self.moveto(cx + r, cy)
        self.curveto(cx + r, cy + k, cx + k, cy + r, cx, cy + r)
        self.curveto(cx - k, cy + r, cx - r, cy + k, cx - r, cy)
        self.curveto(cx - r, cy - k, cx - k, cy - r, cx, cy - r)
        self.curveto(cx + k, cy - r, cx + r, cy - k, cx + r, cy)
        self.close()

    def circle(self, cx, cy, r, mode="S"):
        self.circle_path(cx, cy, r)
        self.ops.append(mode)

    def ellipse(self, cx, cy, rx, ry, mode="S"):
        kx, ky = 0.5522847498 * rx, 0.5522847498 * ry
        self.moveto(cx + rx, cy)
        self.curveto(cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry)
        self.curveto(cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy)
        self.curveto(cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry)
        self.curveto(cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy)
        self.close()
        self.ops.append(mode)

    def roundrect_path(self, x0, y0, x1, y1, r):
        k = 0.5522847498 * r
        self.moveto(x0 + r, y0)
        self.lineto(x1 - r, y0)
        self.curveto(x1 - r + k, y0, x1, y0 + r - k, x1, y0 + r)
        self.lineto(x1, y1 - r)
        self.curveto(x1, y1 - r + k, x1 - r + k, y1, x1 - r, y1)
        self.lineto(x0 + r, y1)
        self.curveto(x0 + r - k, y1, x0, y1 - r + k, x0, y1 - r)
        self.lineto(x0, y0 + r)
        self.curveto(x0, y0 + r - k, x0 + r - k, y0, x0 + r, y0)
        self.close()

    def roundrect(self, x0, y0, x1, y1, r, mode="S"):
        self.roundrect_path(x0, y0, x1, y1, r)
        self.ops.append(mode)

    def arrowhead(self, x, y, ang, size=6.0):
        """Solid triangular head pointing along `ang` (radians)."""
        a = ang
        p0 = (x, y)
        p1 = (x - size * math.cos(a) + size * 0.42 * math.sin(a),
              y - size * math.sin(a) - size * 0.42 * math.cos(a))
        p2 = (x - size * math.cos(a) - size * 0.42 * math.sin(a),
              y - size * math.sin(a) + size * 0.42 * math.cos(a))
        self.polyline([p0, p1, p2], closed=True, mode="f")

    def content(self):
        return "\n".join(self.ops)


def write_pdf(path, canvas):
    stream = canvas.content().encode("latin-1")
    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %g %g] "
                 "/Contents 4 0 R /Resources << >> >>" % (W, H)).encode())
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
                + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref))
    open(path, "wb").write(bytes(out))


# ---------------------------------------------------------------- palette
STRUCT = 0.52     # machine housing
DETAIL = 0.62     # small parts / material
FOUND = 0.16      # the solution path -- the only "loud" element
LW_HOUSE = 1.5
LW_PART = 1.1
LW_FINE = 0.8

c = Canvas()


def bar(x, y, w, h=6.0, gray=DETAIL, lw=LW_PART):
    c.gs(lw=lw, gray=gray)
    c.roundrect(x, y, x + w, y + h, h / 2.0)
    c.grestore()


def tilted_bar(cx, cy, w, ang, h=6.0, gray=DETAIL, lw=LW_PART):
    """A code line riding an inclined belt."""
    ca, sa = math.cos(ang), math.sin(ang)
    c.gs(lw=lw, gray=gray)
    c.ops.append("1 g")                       # opaque: it rides over the belt
    c.ops.append("%s cm" % c._f(ca, sa, -sa, ca, cx, cy))
    c.roundrect(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0, h / 2.0)
    c.ops.append("B")
    c.grestore()


def dot(cx, cy, r, filled=False, gray=DETAIL, lw=LW_PART, opaque=False):
    c.gs(lw=lw, gray=gray)
    if filled:
        c.circle(cx, cy, r, mode="f")
    elif opaque:
        c.ops.append("1 g")
        c.circle(cx, cy, r, mode="B")
    else:
        c.circle(cx, cy, r, mode="S")
    c.grestore()


def gear(cx, cy, r_out, r_in, teeth, phase=0.0):
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a = phase + i * step
        for frac, r in ((0.00, r_in), (0.14, r_out), (0.36, r_out), (0.50, r_in)):
            ang = a + frac * step
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    c.gs(lw=LW_PART, gray=STRUCT)
    c.polyline(pts, closed=True)
    c.circle(cx, cy, r_in * 0.34)
    c.grestore()


def bug_glyph(cx, cy, s=1.0):
    """The defect itself: a small beetle sitting in the broken line."""
    rx, ry = 5.4 * s, 3.7 * s
    c.gs(lw=0.85 * s, gray=FOUND)
    for dx in (-3.6 * s, 0.0, 3.0 * s):          # legs, off the body outline
        edge = ry * math.sqrt(max(0.0, 1.0 - (dx / rx) ** 2))
        for sgn in (1, -1):
            c.line(cx + dx, cy + sgn * edge,
                   cx + dx - 2.7 * s, cy + sgn * (edge + 3.2 * s))
    c.grestore()
    c.gs(lw=1.05 * s, gray=FOUND)
    c.ellipse(cx, cy, rx, ry)
    c.line(cx - rx + 1.6 * s, cy, cx + rx - 1.6 * s, cy)      # elytra seam
    c.grestore()
    c.gs(lw=0.85 * s, gray=FOUND)
    c.circle(cx + rx + 1.0 * s, cy, 2.0 * s)                  # head
    c.line(cx + rx + 2.2 * s, cy + 1.4 * s, cx + rx + 5.2 * s, cy + 3.2 * s)
    c.line(cx + rx + 2.2 * s, cy - 1.4 * s, cx + rx + 5.2 * s, cy - 3.2 * s)
    c.grestore()


def template_glyph(cx, cy, s=1.0):
    """A mined template: a small tree whose leaves are open holes."""
    c.gs(lw=LW_FINE, gray=DETAIL)
    c.line(cx, cy + 6 * s, cx, cy + 2 * s)
    c.line(cx - 6 * s, cy - 3 * s, cx + 6 * s, cy - 3 * s)
    c.line(cx - 6 * s, cy - 3 * s, cx - 6 * s, cy - 1 * s)
    c.line(cx + 6 * s, cy - 3 * s, cx + 6 * s, cy - 1 * s)
    c.moveto(cx - 6 * s, cy - 3 * s)
    c.lineto(cx, cy + 2 * s)
    c.lineto(cx + 6 * s, cy - 3 * s)
    c.stroke()
    c.circle(cx, cy + 7.5 * s, 1.8 * s)
    c.circle(cx - 6 * s, cy - 5.5 * s, 2.4 * s)
    c.circle(cx + 6 * s, cy - 5.5 * s, 2.4 * s)
    c.grestore()


def _place(cx, cy, ang):
    c.ops.append("1 g")
    ca, sa = math.cos(ang), math.sin(ang)
    c.ops.append("%s cm" % c._f(ca, sa, -sa, ca, cx, cy))


def square_glyph(cx, cy, side, ang=0.0, gray=DETAIL, lw=LW_PART):
    c.gs(lw=lw, gray=gray)
    _place(cx, cy, ang)
    c.roundrect(-side / 2.0, -side / 2.0, side / 2.0, side / 2.0, 0.8, mode="B")
    c.grestore()


def triangle_glyph(cx, cy, base, ang=0.0, gray=DETAIL, lw=LW_PART):
    h = base * 0.87
    c.gs(lw=lw, gray=gray)
    _place(cx, cy, ang)
    c.polyline([(-base / 2.0, -h / 2.0), (base / 2.0, -h / 2.0), (0, h / 2.0)],
               closed=True, mode="B")
    c.grestore()


def pipe(pts, gray=STRUCT, lw=LW_HOUSE, head=True, headsize=6.5, dash=None):
    pts = list(pts)
    tip = ang = None
    if head:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        ang = math.atan2(y1 - y0, x1 - x0)
        tip = (x1, y1)
        trim = headsize - lw            # stroke ends inside the head, not past it
        pts[-1] = (x1 - trim * math.cos(ang), y1 - trim * math.sin(ang))
    c.gs(lw=lw, gray=gray, dash=dash)
    c.moveto(*pts[0])
    for p in pts[1:]:
        c.lineto(*p)
    c.stroke()
    c.grestore()
    if head:
        c.gs(lw=lw, gray=gray)
        c.arrowhead(tip[0], tip[1], ang, headsize)
        c.grestore()


# --- the search over the grammar: many branches explored, one path found
import random

LEVEL_X = [206.0, 262.0, 316.0, 366.0, 410.0]
BRANCH = {0: [3], 1: [2, 3, 2], 2: [1, 2, 2, 3], 3: [0, 1, 2, 0, 2]}


def build(depth, rng):
    jitter = 0.0 if depth < 2 else rng.uniform(-7.0, 7.0)
    node = {"depth": depth, "x": LEVEL_X[depth] + jitter}
    node["children"] = ([] if depth == len(LEVEL_X) - 1
                        else [build(depth + 1, rng)
                              for _ in range(rng.choice(BRANCH[depth]))])
    return node


def layout(node, slot):
    if not node["children"]:
        node["y"] = next(slot)
        return
    for k in node["children"]:
        layout(k, slot)
    node["y"] = sum(k["y"] for k in node["children"]) / float(len(node["children"]))


def leaves(node):
    if not node["children"]:
        yield node
    else:
        for k in node["children"]:
            for l in leaves(k):
                yield l


def chain_to(node, target):
    if node is target:
        return [node]
    for k in node["children"]:
        sub = chain_to(k, target)
        if sub:
            return [node] + sub
    return None


SEED = int(os.environ.get("SEED", "7"))   # fixed: the drawing is reproducible
root = build(0, random.Random(SEED))
n = sum(1 for _ in leaves(root))
YMIN, YMAX = 118.0, 276.0
step = (YMAX - YMIN) / float(n - 1)
layout(root, iter([YMIN + i * step for i in range(n)]))

deep = [l for l in leaves(root) if l["depth"] == len(LEVEL_X) - 1]
target = min(deep, key=lambda nd: abs(nd["y"] - 262.0))
path = chain_to(root, target)
PATH_IDS = set(id(x) for x in path)
PATH_EDGES = set((id(a), id(b)) for a, b in zip(path, path[1:]))

# The root of the search tree fixes the height of the whole intake run:
# the ball leaving the grader, the pipe, and the root all sit on INLET_Y.
INLET_Y = root["y"]

# ================================================================= base frame
RAIL_Y = 32.0
c.gs(lw=LW_HOUSE, gray=STRUCT)
c.line(22, RAIL_Y, 581, RAIL_Y)
c.grestore()
for fx in (92, 300, 512):
    c.gs(lw=LW_HOUSE, gray=STRUCT)
    c.polyline([(fx - 9, RAIL_Y), (fx - 13, 21), (fx + 13, 21), (fx + 9, RAIL_Y)])
    c.grestore()

# ============================================== A. buggy program -> the funnel
STACK_X = 34.0
for i, (w, y) in enumerate(zip([66, 52, 72, 46, 44],
                               [358, 346, 332, 318, 306])):
    if i == 2:                                   # the defect: a broken line
        bar(STACK_X, y, 22)
        bar(STACK_X + 50, y, w - 50)
        bug_glyph(STACK_X + 33, y + 3.0, 1.2)
    else:
        bar(STACK_X, y, w)

c.gs(lw=LW_HOUSE, gray=STRUCT)
c.polyline([(26, 300), (76, 258), (76, 248)])
c.polyline([(146, 300), (96, 258), (96, 248)])
c.grestore()
dot(86, 288, 3.2)
dot(74, 274, 2.4)

# ============================================ B. fault localisation: a grader
# Both screens are the same length. The lower one's lip is set so that a ball
# resting on it would sit at INLET_Y; the selected location is drawn just clear
# of that lip, so it reads as having rolled off rather than still sitting on it.
BALL_R = 6.6
SCR_X0, SCR_X1 = 32.0, 142.0                  # same span as the upper screen
SCR_FALL = -24.0
_sl = math.hypot(SCR_X1 - SCR_X0, SCR_FALL)
SN = (-SCR_FALL / _sl, (SCR_X1 - SCR_X0) / _sl)   # upward normal of the screen
BALL_X = SCR_X1 + SN[0] * BALL_R + 7.0      # clear of the lip
SCREEN = ((SCR_X0, INLET_Y - SN[1] * BALL_R - SCR_FALL),
          (SCR_X1, INLET_Y - SN[1] * BALL_R))
c.gs(lw=LW_HOUSE, gray=STRUCT)
c.line(26, 250, 26, RAIL_Y)
c.line(148, 250, 148, INLET_Y + BALL_R + 4)   # right wall, ported where the
c.line(148, INLET_Y - BALL_R - 5, 148, RAIL_Y)  # location is tapped off
c.line(26, 250, 60, 250)
c.line(112, 250, 148, 250)
c.grestore()

for (x0, y0), (x1, y1) in (((32, 238), (142, 214)), SCREEN):
    c.gs(lw=LW_PART, gray=STRUCT)
    c.line(x0, y0, x1, y1)
    c.grestore()
    c.gs(lw=LW_FINE, gray=DETAIL)
    for i in range(1, 9):
        t = i / 9.0
        px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        c.line(px, py, px + 1.2, py + 4.5)
    c.grestore()

# candidates ranked by suspiciousness; the coarsest one survives both screens
for x, r in ((46, 3.0), (68, 4.2), (92, 5.4), (118, 6.6)):
    t = (x - 32) / 110.0
    dot(x, 238 - 24 * t + r + 1.0, r)
dot(58, 197, 2.6)
dot(86, 190, 2.0)
# statements that fall through pile up as discarded material
for hx, hy, hr in ((60, 172, 2.2), (104, 166, 1.8), (82, 150, 2.4),
                   (46, 132, 1.9), (118, 128, 2.2)):
    dot(hx, hy, hr, gray=0.72, lw=LW_FINE)
HEAP = [(7, 39.5), (6, 51.0), (4, 62.5), (2, 74.0)]
for count, hy in HEAP:
    for i in range(count):
        dot(87 + (i - (count - 1) / 2.0) * 15.0, hy, 2.9,
            gray=0.72, lw=LW_FINE)

# the most suspicious location is tapped off to the core
dot(BALL_X, INLET_Y, BALL_R, gray=FOUND, lw=LW_PART)
pipe([(BALL_X + BALL_R + 1.5, INLET_Y), (190, INLET_Y)], gray=STRUCT)

# =============================================== C. template mill -> grammar
DR = (256.0, 304.0, 390.0, 350.0)
# an inclined belt carries the very same code lines up into the mill
BELT0, BELT1, BELT_R = (102.0, 314.0), (150.0, 337.0), 6.5
bdx, bdy = BELT1[0] - BELT0[0], BELT1[1] - BELT0[1]
BELT_A = math.atan2(bdy, bdx)
nx, ny = -math.sin(BELT_A), math.cos(BELT_A)
# the lines ride behind the belt, so the belt itself stays unbroken
for t, bw in ((0.32, 14), (0.60, 12), (0.86, 9)):
    lift = BELT_R + 3.0                       # bar underside on the belt line
    tilted_bar(BELT0[0] + t * bdx + nx * lift,
               BELT0[1] + t * bdy + ny * lift, bw, BELT_A)
c.gs(lw=LW_PART, gray=STRUCT)
c.circle(BELT0[0], BELT0[1], BELT_R)
c.circle(BELT1[0], BELT1[1], BELT_R)
for sgn in (1, -1):
    c.line(BELT0[0] + sgn * nx * BELT_R, BELT0[1] + sgn * ny * BELT_R,
           BELT1[0] + sgn * nx * BELT_R, BELT1[1] + sgn * ny * BELT_R)
c.grestore()
c.gs(lw=LW_HOUSE, gray=STRUCT)
c.line(148, 250, 148, 328.5)          # post carrying the head of the belt
c.grestore()
gear(186, 338, 27, 20, 12, phase=0.13)
gear(230, 322, 19, 13.5, 9, phase=0.31)
pipe([(249, 315), (255.2, 317.4)], gray=DETAIL, lw=LW_PART, head=False)

c.gs(lw=LW_HOUSE, gray=STRUCT)
c.roundrect(DR[0], DR[1], DR[2], DR[3], 12)
c.grestore()
for gx in (282, 323, 364):
    template_glyph(gx, 326, 0.95)
c.gs(lw=LW_HOUSE, gray=STRUCT)          # neck: grammar into the core
c.polyline([(302, 304), (308, 296)])
c.polyline([(348, 304), (342, 296)])
c.grestore()

# ==================================================== D. the synthesis core
BOX = (190.0, 96.0, 430.0, 296.0)
c.gs(lw=LW_HOUSE, gray=STRUCT)
c.roundrect(BOX[0], BOX[1], BOX[2], BOX[3], 11)
c.grestore()
for lx in (212, 408):
    c.gs(lw=LW_HOUSE, gray=STRUCT)
    c.line(lx, 96, lx, RAIL_Y)
    c.grestore()

def draw_tree(node, depth, want_path):
    """Two passes: the explored branches first, the found path on top."""
    x = node["x"]
    for k in node["children"]:
        kx = k["x"]
        on = (id(node), id(k)) in PATH_EDGES
        if on == want_path:
            c.gs(lw=2.5 if on else 0.95, gray=FOUND if on else 0.68)
            c.moveto(x, node["y"])
            mx = (x + kx) / 2.0
            c.curveto(mx, node["y"], mx, k["y"], kx, k["y"])
            c.stroke()
            c.grestore()
        draw_tree(k, depth + 1, want_path)
    on = id(node) in PATH_IDS
    if on != want_path:
        return
    if not node["children"] and on:
        dot(x, node["y"], 4.6, filled=True, gray=FOUND)
        dot(x, node["y"], 8.0, gray=FOUND, lw=1.0)
    elif on:
        dot(x, node["y"], 3.4, filled=True, gray=FOUND)
    else:
        dot(x, node["y"], 2.5, gray=0.68, lw=0.95)
        if depth < len(LEVEL_X) - 1:        # pruned: the branch dies here
            c.gs(lw=0.95, gray=0.68)
            c.line(x + 6.5, node["y"] - 3.5, x + 6.5, node["y"] + 3.5)
            c.grestore()


draw_tree(root, 0, False)
draw_tree(root, 0, True)
EXIT_Y = target["y"]

# ====================================== E. the test suite: a shape sorter
# Each test is a sloped plate with an aperture. A candidate that fits drops
# through all of them into the tray; one that does not slides down the slope
# and out of a slot in the wall, into the line that returns it to the search.
VX0, VX1, VY0, VY1 = 456.0, 578.0, 128.0, 276.0
SPOUT_X = 437.0                                # plates run out through the wall
HOLE = (509.0, 523.0)
AXIS = 516.0
DROP = 16.0                                   # how far the plates fall to the left
GATE_Y = [246.0, 202.0, 158.0]


def plate_y(gy, x):
    return gy - DROP + (x - VX0) / (VX1 - VX0) * DROP


pipe([(430, EXIT_Y), (AXIS, EXIT_Y), (AXIS, 256)], gray=STRUCT)

c.gs(lw=LW_HOUSE, gray=STRUCT)
c.line(VX0, VY1, VX0, EXIT_Y + 7)             # left wall, slotted at each plate
c.line(VX0, EXIT_Y - 7, VX0, 248)             # each plate discharges through
c.line(VX0, 226, VX0, 204)                    # the port above it
c.line(VX0, 182, VX0, 160)
c.line(VX0, 140, VX0, VY0)
c.line(VX1, VY1, VX1, VY0)
c.line(VX0, VY1, VX1, VY1)
c.grestore()

# too wide for the aperture: sliding down the plate and out of the slot.
# Drawn before the plates, and sunk a little into them, so the plate stroke
# covers the join instead of leaving a ragged sliver of white.
PLATE_A = math.atan2(DROP, VX1 - VX0)
PN = (-math.sin(PLATE_A), math.cos(PLATE_A))


def resting(x, gy, lift):
    return x + PN[0] * lift, plate_y(gy, x) + PN[1] * lift


# bottom edge centred on the plate's centre line: its 1.1pt stroke sits wholly
# inside the plate's 1.5pt one, so nothing shows above or below
SIT = 0.0
square_glyph(*resting(492, GATE_Y[0], 9.0 + SIT), side=18, ang=PLATE_A)
triangle_glyph(*resting(446, GATE_Y[1], 16 * 0.87 / 2.0 + SIT), base=16,
               ang=PLATE_A)

for gy in GATE_Y:
    # plate and aperture collar are one stroke, so the corner closes cleanly
    c.gs(lw=LW_HOUSE, gray=STRUCT)
    c.polyline([(SPOUT_X, plate_y(gy, SPOUT_X)),
                (HOLE[0], plate_y(gy, HOLE[0])),
                (HOLE[0], plate_y(gy, HOLE[0]) - 5)])
    c.polyline([(HOLE[1], plate_y(gy, HOLE[1]) - 5),
                (HOLE[1], plate_y(gy, HOLE[1])),
                (VX1, plate_y(gy, VX1))])
    c.grestore()

c.gs(lw=LW_FINE, gray=0.76, dash=[3.0, 3.0])  # the drop axis through the tests
c.line(AXIS, 250, AXIS, 110)
c.grestore()

# the candidate that fits, falling through every test into the tray
dot(AXIS, 215, 5.0, gray=FOUND, lw=1.1, opaque=True)
dot(AXIS, 171, 5.0, gray=FOUND, lw=1.1, opaque=True)
dot(AXIS, 118, 5.0, filled=True, gray=FOUND)

# rejected candidates: back to the search -- same weight and head as every
# other run in the machine, dashed only to mark it as the return leg
pipe([(437, 240), (437, 72), (258, 72), (258, 96)], gray=STRUCT,
     dash=[4.5, 3.5])

# ==================================================== F. the patched program
TR = (464.0, 54.0, 578.0, 106.0)
c.gs(lw=LW_HOUSE, gray=STRUCT)
c.polyline([(TR[0], TR[3]), (TR[0], TR[1]), (TR[2], TR[1]), (TR[2], TR[3])])
c.grestore()
for px in (486, 558):
    c.gs(lw=LW_HOUSE, gray=STRUCT)
    c.line(px, TR[1], px, RAIL_Y)
    c.grestore()
for i, (w, y) in enumerate(zip([88, 64, 92, 58], (92, 82, 72, 62))):
    bar(476, y, w, 6, gray=FOUND if i == 2 else DETAIL, lw=LW_PART)

write_pdf("machine.pdf", c)
print("wrote machine.pdf")

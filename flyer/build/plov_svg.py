"""Generates a top-down illustration of Uzbek plov on a Rishtan-style lyagan plate (SVG)."""
import math
import random

random.seed(7)
C = 400  # centre of the 800x800 viewBox


def blob(cx, cy, r, n=9, jitter=0.28, rot=0.0, sx=1.0, sy=1.0):
    pts = []
    for i in range(n):
        a = rot + 2 * math.pi * i / n
        rr = r * (1 + random.uniform(-jitter, jitter))
        pts.append((cx + rr * math.cos(a) * sx, cy + rr * math.sin(a) * sy))
    d = []
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        if i == 0:
            d.append(f"M{p1[0]:.1f},{p1[1]:.1f}")
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return "".join(d) + "Z"


def rand_in_disc(R, bias=0.5):
    r = R * (random.random() ** bias)
    a = random.uniform(0, 2 * math.pi)
    return C + r * math.cos(a), C + r * math.sin(a), r


def plate():
    s = []
    # shadow + rim
    s.append(f'<ellipse cx="{C+10}" cy="{C+22}" rx="388" ry="384" fill="#000" opacity=".45" filter="url(#pv-blur)"/>')
    s.append(f'<circle cx="{C}" cy="{C}" r="385" fill="url(#pv-rim)"/>')
    s.append(f'<circle cx="{C}" cy="{C}" r="372" fill="none" stroke="#1d3f86" stroke-width="7"/>')
    s.append(f'<circle cx="{C}" cy="{C}" r="362" fill="none" stroke="#c99a3c" stroke-width="2"/>')
    # Rishtan-style almond (bodom) petals around the rim
    n = 28
    for i in range(n):
        a = 360 * i / n
        s.append(
            f'<g transform="rotate({a:.2f} {C} {C})">'
            f'<path d="M{C},{C-358} C{C+13},{C-345} {C+12},{C-326} {C},{C-318} C{C-12},{C-326} {C-13},{C-345} {C},{C-358}Z" fill="#2453a6"/>'
            f'<path d="M{C},{C-350} C{C+6},{C-342} {C+6},{C-332} {C},{C-326} C{C-6},{C-332} {C-6},{C-342} {C},{C-350}Z" fill="#3ea7b8"/>'
            f'<circle cx="{C}" cy="{C-312}" r="2.6" fill="#c99a3c"/></g>'
        )
        b = a + 180 / n
        s.append(f'<circle cx="{C}" cy="{C-352}" r="3.2" fill="#1d3f86" transform="rotate({b:.2f} {C} {C})"/>')
    s.append(f'<circle cx="{C}" cy="{C}" r="306" fill="none" stroke="#1d3f86" stroke-width="4"/>')
    s.append(f'<circle cx="{C}" cy="{C}" r="300" fill="url(#pv-well)"/>')
    return s


def rice():
    s = []
    R = 288
    s.append(f'<circle cx="{C}" cy="{C}" r="{R+4}" fill="#000" opacity=".25" filter="url(#pv-soft)"/>')
    s.append(f'<circle cx="{C}" cy="{C}" r="{R}" fill="url(#pv-rice)"/>')
    cols = ["#f8e4ae", "#f3d48e", "#eec46e", "#fbecc6", "#e8b65c", "#f6dc9c", "#e2a94e"]
    grains = []
    for _ in range(4800):
        x, y, r = rand_in_disc(R - 4, 0.5)
        ang = random.uniform(0, 180)
        k = r / R
        col = random.choice(cols if k < 0.8 else cols[2:5] + ["#d29a45"])
        L = random.uniform(7.0, 9.0)
        grains.append(
            f'<g transform="rotate({ang:.0f} {x:.1f} {y:.1f})">'
            f'<ellipse cx="{x+.6:.1f}" cy="{y+1.1:.1f}" rx="{L:.1f}" ry="2.6" fill="#9a6224" opacity=".45"/>'
            f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{L:.1f}" ry="2.4" fill="{col}"/>'
            f'<ellipse cx="{x-1:.1f}" cy="{y-.8:.1f}" rx="{L*.55:.1f}" ry=".7" fill="#fffaf0" opacity=".65"/></g>'
        )
    return s, grains


def carrots(count, Rmax):
    s = []
    cols = ["#ec6a12", "#f5821c", "#e0560f", "#f8952c", "#e8700f"]
    for _ in range(count):
        x, y, r = rand_in_disc(Rmax, 0.7)
        L = random.uniform(26, 46)
        ang = random.uniform(0, 180)
        col = random.choice(cols)
        s.append(
            f'<g transform="rotate({ang:.0f} {x:.1f} {y:.1f})">'
            f'<rect x="{x-L/2+.8:.1f}" y="{y-2.2:.1f}" width="{L:.1f}" height="7" rx="3" fill="#8a3108" opacity=".45"/>'
            f'<rect x="{x-L/2:.1f}" y="{y-3.3:.1f}" width="{L:.1f}" height="6.6" rx="3" fill="{col}"/>'
            f'<rect x="{x-L/2+3:.1f}" y="{y-2.3:.1f}" width="{L-8:.1f}" height="1.6" rx=".8" fill="#ffd09a" opacity=".75"/></g>'
        )
    return s


def chickpeas(count, Rmax):
    s = []
    for _ in range(count):
        x, y, _ = rand_in_disc(Rmax, 0.6)
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="url(#pv-pea)" stroke="#9c6a26" stroke-width=".8"/>'
                 f'<path d="M{x-2:.1f},{y-6:.1f} q2,4 0,8" stroke="#b07a2c" stroke-width="1" fill="none" opacity=".6"/>')
    return s


def meat():
    s = []
    spots = [(0, 0)]
    for i in range(10):
        a = 2 * math.pi * i / 10 + random.uniform(-.2, .2)
        rr = random.uniform(95, 150)
        spots.append((rr * math.cos(a), rr * math.sin(a)))
    for i in range(6):
        a = 2 * math.pi * i / 6 + .5
        spots.append((55 * math.cos(a), 55 * math.sin(a)))
    for dx, dy in spots[1:]:
        x, y = C + dx, C + dy
        r = random.uniform(24, 34)
        rot = random.uniform(0, 6)
        sx = random.uniform(.8, 1.25)
        s.append(f'<path d="{blob(x+4, y+6, r, rot=rot, sx=sx)}" fill="#3a1a0a" opacity=".45" filter="url(#pv-soft)"/>')
        s.append(f'<path d="{blob(x, y, r, rot=rot, sx=sx)}" fill="url(#pv-meat)"/>')
        s.append(f'<path d="{blob(x-r*.25, y-r*.3, r*.45, jitter=.35)}" fill="#e0965a" opacity=".45"/>')
        s.append(f'<ellipse cx="{x-r*.3:.1f}" cy="{y-r*.35:.1f}" rx="{r*.22:.1f}" ry="{r*.09:.1f}" fill="#fff3e0" opacity=".55" transform="rotate(-30 {x-r*.3:.1f} {y-r*.35:.1f})"/>')
        s.append(f'<path d="M{x-r*.6:.1f},{y+r*.1:.1f} q{r*.5:.1f},{-r*.3:.1f} {r*1.1:.1f},{r*.05:.1f}" stroke="#2f1206" stroke-width="1.6" fill="none" opacity=".5"/>')
    return s


def garlic():
    x = y = C
    s = [f'<ellipse cx="{x+8}" cy="{y+12}" rx="58" ry="56" fill="#2a1206" opacity=".55" filter="url(#pv-soft)"/>',
         f'<circle cx="{x}" cy="{y}" r="56" fill="url(#pv-bulb)"/>']
    # clove seams converging on the root
    for i in range(9):
        a = 360 * i / 9 + 10
        s.append(f'<path d="M{x},{y} C{x+22},{y-12} {x+30},{y-38} {x+14},{y-55}" stroke="#a9785a" stroke-width="1.6" fill="none" opacity=".6" transform="rotate({a} {x} {y})"/>')
    s.append(f'<circle cx="{x}" cy="{y}" r="11" fill="#b78a5a"/><circle cx="{x}" cy="{y}" r="6" fill="#7d5128"/>')
    for i in range(12):
        a = 30 * i
        s.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y-9}" stroke="#5c3a1a" stroke-width="1.2" transform="rotate({a} {x} {y})"/>')
    s.append(f'<ellipse cx="{x-22}" cy="{y-26}" rx="16" ry="7" fill="#fff" opacity=".5" transform="rotate(-38 {x-22} {y-26})"/>')
    return s


def toppings():
    s = []
    for _ in range(18):  # raisins
        x, y, _ = rand_in_disc(250, 0.6)
        s.append(f'<path d="{blob(x, y, 5.5, n=6, jitter=.3)}" fill="#3b1a14"/>')
    for _ in range(90):  # cumin / zira seeds
        x, y, _ = rand_in_disc(270, 0.55)
        a = random.uniform(0, 180)
        s.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="2.6" ry=".9" fill="#5a3a1c" transform="rotate({a:.0f} {x:.1f} {y:.1f})"/>')
    return s


def defs():
    return """<defs>
<filter id="pv-blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="14"/></filter>
<filter id="pv-soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="4"/></filter>
<radialGradient id="pv-rim" cx="45%" cy="40%" r="65%"><stop offset="0" stop-color="#fffdf6"/><stop offset=".8" stop-color="#f1e9d6"/><stop offset="1" stop-color="#d8cbb0"/></radialGradient>
<radialGradient id="pv-well" cx="50%" cy="50%" r="50%"><stop offset=".85" stop-color="#f4ecd9"/><stop offset="1" stop-color="#cdbd9c"/></radialGradient>
<radialGradient id="pv-rice" cx="46%" cy="42%" r="58%"><stop offset="0" stop-color="#f2c873"/><stop offset=".7" stop-color="#d99a3e"/><stop offset="1" stop-color="#a5661f"/></radialGradient>
<radialGradient id="pv-meat" cx="35%" cy="30%" r="80%"><stop offset="0" stop-color="#c0602a"/><stop offset=".5" stop-color="#843210"/><stop offset="1" stop-color="#3e1505"/></radialGradient>
<radialGradient id="pv-pea" cx="35%" cy="30%" r="75%"><stop offset="0" stop-color="#fbe4a6"/><stop offset=".7" stop-color="#deae5c"/><stop offset="1" stop-color="#a87530"/></radialGradient>
<radialGradient id="pv-clove" cx="40%" cy="30%" r="80%"><stop offset="0" stop-color="#fffaf2"/><stop offset=".6" stop-color="#f0dccb"/><stop offset="1" stop-color="#c79c86"/></radialGradient>
<radialGradient id="pv-bulb" cx="38%" cy="32%" r="75%"><stop offset="0" stop-color="#fff9ee"/><stop offset=".55" stop-color="#efd6bd"/><stop offset=".85" stop-color="#cf9c74"/><stop offset="1" stop-color="#9c6a44"/></radialGradient>
<radialGradient id="pv-shine" cx="38%" cy="32%" r="55%"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
</defs>"""


def build():
    base, grains = rice()
    parts = [defs()] + plate() + base
    parts += grains[:3600]
    parts += carrots(260, 272)
    parts += chickpeas(28, 240)
    parts += grains[3600:]
    parts += carrots(110, 220)
    parts += meat()
    parts += garlic()
    parts += toppings()
    parts.append(f'<circle cx="{C}" cy="{C}" r="288" fill="url(#pv-shine)"/>')
    return "\n".join(parts)


if __name__ == "__main__":
    body = build()
    with open("plov_symbol.svg", "w") as f:
        f.write(body)
    with open("plov.svg", "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -20 840 860">{body}</svg>')

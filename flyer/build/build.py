import base64, urllib.parse
def tile(col):
    # interlaced 8-point star (girih) lattice tile
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 60"><g fill="none" stroke="{col}" stroke-width="1.4">
<path d="M30 12 L35 25 L48 30 L35 35 L30 48 L25 35 L12 30 L25 25Z"/>
<rect x="19" y="19" width="22" height="22" transform="rotate(45 30 30)"/>
<rect x="19" y="19" width="22" height="22"/>
<path d="M0 0 L12 12 M60 0 L48 12 M0 60 L12 48 M60 60 L48 48 M30 0 V8 M30 60 V52 M0 30 H8 M60 30 H52"/>
<circle cx="30" cy="30" r="4"/><circle cx="0" cy="0" r="6"/><circle cx="60" cy="0" r="6"/><circle cx="0" cy="60" r="6"/><circle cx="60" cy="60" r="6"/>
</g></svg>'''
    return 'data:image/svg+xml,'+urllib.parse.quote(svg)
h=open('template.html').read()
h=h.replace('/*FONTS*/',open('fonts.css').read())
h=h.replace('PATTERN_GOLD',tile('#f1d48c')).replace('PATTERN_RED',tile('#7a1416'))
h=h.replace('PLOV_IMG','data:image/png;base64,'+base64.b64encode(open('plov.png','rb').read()).decode())
open('../saydali-flyer.html','w').write(h)

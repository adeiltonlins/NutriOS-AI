import re, os, glob
from collections import defaultdict

refs = defaultdict(set)
for f in sorted(glob.glob('app/static/*.html')):
    txt = open(f, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'href="(/static/([^"]+?))"', txt):
        full = m.group(1)
        if not full.endswith('.css'):
            continue
        base = full.split('?')[0].split('/')[-1]
        refs[base].add(os.path.basename(f))

allcss = sorted(os.path.basename(x) for x in glob.glob('app/static/*.css'))
referenced = set(refs.keys())
dead = sorted(set(allcss) - referenced)

print("== Referenced CSS per template (top-level app/static) ==")
for base in allcss:
    if base in refs:
        print(base, "->", len(refs[base]), "file(s):", ', '.join(sorted(refs[base])))

print("\n== DEAD css files (not referenced by any top-level template) ==")
for d in dead:
    print("  ", d)

print("\n== Nested /static/static/ css references from top-level templates? ==")
nested = set()
for f in sorted(glob.glob('app/static/*.html')):
    txt = open(f, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'/static/static/([^"/]+\.css)', txt):
        nested.add(m.group(1))
print("  none" if not nested else ", ".join(sorted(nested)))

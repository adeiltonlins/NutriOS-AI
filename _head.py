import re, glob
for f in ['app/static/app.html', 'app/static/clinical-dashboard.html', 'app/static/patient-portal.html', 'app/static/admin.html']:
    txt = open(f, encoding='utf-8', errors='replace').read()
    print('====', f, '====')
    links = re.findall(r'href="(/static/[^"]+?)"', txt)
    for l in links:
        print('  ', l)
    print()

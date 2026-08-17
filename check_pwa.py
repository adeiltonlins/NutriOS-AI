import re
html = open('C:/Users/Windows 11/.openclaw/workspace/NutriOS-AI/app/static/app.html', encoding='utf-8').read()
checks = ['rel="manifest"', '/static/manifest.json', 'apple-touch-icon', 'serviceWorker.register', '/static/sw.js', 'theme-color']
for c in checks:
    print(c, '->', c in html)

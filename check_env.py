import sys, importlib
mods = ['requests','dotenv','apscheduler','pytz']
print('Python:', sys.version)
status = {}
for m in mods:
    try:
        importlib.import_module(m)
        status[m] = True
    except Exception as e:
        status[m] = False
        print(f'{m}: MISS -> {e.__class__.__name__}: {e}')
for m in mods:
    if status.get(m):
        print(f'{m}: OK')
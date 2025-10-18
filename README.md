# GroupThink — Quick Run & Test

Minimal instructions to run the app and run the test suite.

1) Install dependencies

```powershell
python -m pip install -r requirements.txt
```

2) Run migrations and start dev server

```powershell
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000 in your browser.

3) Run tests and coverage

```powershell
python -m pip install pytest pytest-django coverage
coverage run -m pytest -q
coverage report -m
```

If you want only the total coverage line:

```powershell
coverage report -m | Select-String 'TOTAL'
```

That's it — this README intentionally keeps only the bare commands needed to run and test the project.
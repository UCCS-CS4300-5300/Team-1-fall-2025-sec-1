# GroupThink

## Setup Instructions

### 1) Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 2) Set up environment variables

This project uses JaaS (Jitsi as a Service) for video meetings. Create a `.env` file in the project root (same directory as `manage.py`):

```
JAAS_APP_ID=your-app-id
JAAS_API_KEY="-----BEGIN PRIVATE KEY-----\nYOUR_KEY_HERE\n-----END PRIVATE KEY-----"
JAAS_API_KEY_ID=your-key-id
DEBUG=True
```

### 3) Run migrations and start dev server

```powershell
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000 in your browser.

### 4) Run tests and coverage

```powershell
python -m pip install pytest pytest-django coverage
coverage run -m pytest -q
coverage report -m
```

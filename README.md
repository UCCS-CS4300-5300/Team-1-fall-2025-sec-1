# GroupThink

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

Environment variables (JaaS / Jitsi)

This project uses JaaS for video meetings. To generate server-side JWTs the app expects these environment variables to be set:

- `JAAS_APP_ID` - your JaaS Application ID
- `JAAS_API_KEY` - the RSA private key used to sign JWTs (PEM format)
- `JAAS_API_KEY_ID` - the API key id (kid) provided by JaaS

For local development create a `.env` file in the project root (it's already in `.gitignore`). Example `.env` contents:

```
JAAS_APP_ID=your-app-id
JAAS_API_KEY="-----BEGIN PRIVATE KEY-----\nMIIEvgIBADAN...\n-----END PRIVATE KEY-----"
JAAS_API_KEY_ID=your-key-id
```

Notes:
- Keep `.env` out of version control. If your PEM file contains newlines you can either escape them with `\n` inside the `.env` value or load the key into the environment at runtime (for example: `export JAAS_API_KEY="$(cat /path/to/key.pem)"`).
- On GitHub set repository secrets named `JAAS_APP_ID`, `JAAS_API_KEY` and `JAAS_API_KEY_ID` so workflows can access them.

Committing & pushing (quick reminder)

```bash
# create a branch for the sprint
git checkout -b sprint1

# stage and commit
git add -A
git commit -m "Sprint 1: features, tests, docs"

# add remote (replace <your> values) and push main or your branch
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
# or push branch
git push -u origin sprint1
```

If you'd like, paste the output after you run the commit commands and the remote URL (or tell me whether you prefer HTTPS vs SSH) and I'll give exact push commands and verify.

# GroupThink

## Overview
GroupThink is a collaborative Django web application that integrates video meetings using Jitsi as a Service (JaaS). The platform allows teams to meet, manage tasks, and collaborate in real time.

## Setup Instructions

### 1) Install dependencies
```powershell
python -m pip install -r requirements.txt
```

### 2) Set up environment variables
This project uses JaaS (Jitsi as a Service) for video meetings.  
Create a `.env` file in the project root (same directory as `manage.py`):

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

Then open http://127.0.0.1:8000 in your browser.

### 4) Run tests and coverage
```powershell
python -m pip install pytest pytest-django coverage
coverage run -m pytest -q
coverage report -m
```

---

## AI Usage

AI tools were used during the development of this project to assist with various tasks, including:

- Generating and refining Django unit tests  
- Creating and validating views, models, and serializers  
- Performing syntax and style checks for Python and Django files  
- Designing and styling HTML and CSS templates  
- Drafting documentation for the GitHub CI/CD pipeline  
- Implementing functionality for adding and deleting workspaces  
- Using OpenAI’s Whisper model to transcribe team meeting audio recordings  

All AI-assisted outputs were reviewed, tested, and approved by the development team before inclusion in the final project.

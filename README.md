# PrestigeMotors UK 🚗
# test by ahmad
Premium pre-owned car marketplace — Flask + SQLite + GitHub Actions CI/CD.

## 🌐 Live Site
`https://YOURUSERNAME.pythonanywhere.com`

## 🔧 Tech Stack
- **Backend**: Python 3 + Flask
- **Database**: SQLite (images stored as base64 blobs)
- **Frontend**: Vanilla HTML/CSS/JS
- **Hosting**: PythonAnywhere (free tier)
- **CI/CD**: GitHub Actions → PythonAnywhere

## 🚀 Deployment
Every push to `main` automatically deploys to PythonAnywhere.

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for full setup instructions.

## 🔑 Default Login
- URL: `/admin`
- Username: `admin`
- Password: `admin123` ← **change this immediately**

## 📁 Structure
```
├── server.py              # Flask backend + all API routes
├── wsgi.py                # PythonAnywhere WSGI entry point
├── requirements.txt       # Python dependencies
├── Procfile               # Gunicorn start command
├── static/
│   ├── index.html         # Public car listing website
│   └── admin.html         # Admin dashboard
└── .github/
    └── workflows/
        └── deploy.yml     # CI/CD pipeline
```

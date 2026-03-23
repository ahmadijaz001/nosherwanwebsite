# Complete Setup Guide
## GitHub → PythonAnywhere CI/CD for PrestigeMotors UK

---

## PART 1 — Push your code to GitHub

Your repo is: `git@github.com:ahmadijaz001/nosherwanwebsite.git`

### Step 1: Organise your project folder

Make sure your local folder looks like this before pushing:

```
nosherwanwebsite/
├── .github/
│   └── workflows/
│       └── deploy.yml       ← the CI/CD pipeline
├── static/
│   ├── index.html
│   └── admin.html
├── server.py
├── wsgi.py
├── requirements.txt
├── Procfile
├── .gitignore               ← IMPORTANT: stops db/ being pushed
└── README.md
```

### Step 2: Run these commands in your project folder

Open Command Prompt in your `nosherwanwebsite` folder and run:

```bash
# If you haven't initialised git yet:
git init
git remote add origin git@github.com:ahmadijaz001/nosherwanwebsite.git

# Stage all files (db/ is excluded by .gitignore)
git add .

# Check what's being added — make sure db/ is NOT listed
git status

# Commit
git commit -m "Initial commit — PrestigeMotors UK"

# Push to GitHub
git branch -M main
git push -u origin main
```

After this, your code is on GitHub at:
`https://github.com/ahmadijaz001/nosherwanwebsite`

---

## PART 2 — Set up PythonAnywhere (first time only)

### Step 1: Create your free account
Go to https://www.pythonanywhere.com and sign up.
Your username will become part of your URL, e.g. `ahmadijaz001.pythonanywhere.com`

### Step 2: Clone your GitHub repo onto PythonAnywhere
1. In PythonAnywhere dashboard, click **Consoles** → **New Bash console**
2. Run:

```bash
# Clone your repo
git clone https://github.com/ahmadijaz001/nosherwanwebsite.git ~/nosherwanwebsite

# Go into the folder
cd ~/nosherwanwebsite

# Install dependencies
pip install --user flask flask-cors PyJWT gunicorn

# Initialise the database
python wsgi.py
# You should see: ✅ Database initialised
```

### Step 3: Create the Web App
1. Click the **Web** tab at the top of PythonAnywhere
2. Click **Add a new web app**
3. Choose **Manual configuration** (NOT Flask — we want Manual)
4. Select **Python 3.10**
5. Click Next until done

### Step 4: Configure the WSGI file
On the Web tab, find **WSGI configuration file** and click the link to edit it.

**Delete everything in the file** and paste this:

```python
import sys
import os

# Point to your project
project_home = '/home/YOUR_PA_USERNAME/nosherwanwebsite'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Ensure DB directory exists
os.makedirs(os.path.join(project_home, 'db'), exist_ok=True)

# Import app and initialise DB
from server import app, init_db
init_db()

# PythonAnywhere needs a variable called `application`
application = app
```

**Replace `YOUR_PA_USERNAME` with your actual PythonAnywhere username.**

Save the file.

### Step 5: Reload the web app
Click the big green **Reload** button on the Web tab.

Visit `https://YOUR_PA_USERNAME.pythonanywhere.com` — your site should be live! ✅

---

## PART 3 — Set up CI/CD (GitHub Secrets)

This is what makes "push to GitHub → automatically deploy to PythonAnywhere" work.

### Step 1: Get your PythonAnywhere API token
1. Log into PythonAnywhere
2. Click **Account** (top right)
3. Click the **API Token** tab
4. Click **Create a new API token**
5. **Copy the token** — you won't see it again without regenerating

### Step 2: Add secrets to GitHub
1. Go to your GitHub repo: `https://github.com/ahmadijaz001/nosherwanwebsite`
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** for each of these:

| Secret Name      | Value                                  |
|------------------|----------------------------------------|
| `PA_USERNAME`    | Your PythonAnywhere username           |
| `PA_PASSWORD`    | Your PythonAnywhere account password   |
| `PA_API_TOKEN`   | The API token you just copied          |

It should look like this when done:
```
Repository secrets (3):
  PA_USERNAME    ●●●●●●●●●●
  PA_PASSWORD    ●●●●●●●●●●
  PA_API_TOKEN   ●●●●●●●●●●
```

### Step 3: Test the pipeline
Make any small change (e.g. edit README.md) and push:

```bash
echo "# Updated" >> README.md
git add README.md
git commit -m "Test CI/CD pipeline"
git push
```

Then go to your GitHub repo → **Actions** tab.
You'll see the workflow running in real time with green checkmarks ✅

---

## PART 4 — Your workflow going forward

Every time you make a change:

```bash
# 1. Make your changes to any file
# 2. Stage and commit
git add .
git commit -m "describe what you changed"

# 3. Push — this automatically triggers the CI/CD pipeline
git push
```

GitHub Actions will:
1. ✅ Check out your code
2. ✅ SSH into PythonAnywhere
3. ✅ Run `git pull` to get the latest version
4. ✅ Install any new dependencies
5. ✅ Call the PythonAnywhere API to reload your live site
6. ✅ Run a health check to confirm the site is up

**The whole process takes about 30–60 seconds.**

---

## Troubleshooting

### "Permission denied (publickey)" when pushing
You need to add your SSH key to GitHub:
```bash
# Generate a key (if you don't have one)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy the public key
cat ~/.ssh/id_ed25519.pub
```
Then go to GitHub → Settings → SSH Keys → Add New.

Alternatively, use HTTPS instead of SSH:
```bash
git remote set-url origin https://github.com/ahmadijaz001/nosherwanwebsite.git
```

### CI/CD pipeline fails at SSH step
- Double-check `PA_USERNAME` and `PA_PASSWORD` secrets are correct
- PythonAnywhere free accounts DO support SSH — make sure you're using `ssh.pythonanywhere.com`

### Site shows "500 error" after deploy
- Go to PythonAnywhere → Web tab → **Error log**
- Usually means a Python error in server.py

### Database is empty after deploy
- The `db/` folder is in `.gitignore` — this is correct (you don't push data)
- On first deploy the DB is created fresh with sample data
- Your production data lives only on PythonAnywhere — never gets overwritten by code pushes

---

## Quick Reference

| What | Where |
|------|-------|
| Public site | `https://YOUR_PA_USERNAME.pythonanywhere.com` |
| Admin panel | `https://YOUR_PA_USERNAME.pythonanywhere.com/admin` |
| GitHub repo | `https://github.com/ahmadijaz001/nosherwanwebsite` |
| CI/CD logs | GitHub repo → Actions tab |
| PythonAnywhere logs | Web tab → Error log / Server log |
| Change admin password | Admin panel → Settings |

"""
WSGI entry point — used by PythonAnywhere and gunicorn.
PythonAnywhere looks for `application` in this file.
"""
import sys
import os

# Add project folder to path (required by PythonAnywhere)
project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Ensure DB folder exists before first request
os.makedirs(os.path.join(project_home, 'db'), exist_ok=True)

from server import app, init_db

# Initialise database on first run
init_db()

# PythonAnywhere expects `application`
application = app

if __name__ == '__main__':
    app.run()

# GitHub and public deployment guide

## GitHub repository

1. Sign in at GitHub and create a **Public** repository named `malika-garage`.
2. From the `bayflow-website` source folder, upload `server.py`, `app.js`, `index.html`,
   `styles.css`, `README.md`, `requirements.txt`, `.env.example`, and `.gitignore`.
3. Do not upload `.env`, `bayflow.sqlite3`, or the portable `python` runtime folder.
4. Commit the files. The repository URL shown in the address bar is the **GitHub Repo link**.

## Deployment service

This project needs a Python web service, not GitHub Pages. Connect the GitHub repository to
a Python-capable host and configure:

- Build command: `pip install -r requirements.txt`
- Start command: `python server.py`
- Environment variable `BAYFLOW_PASSWORD_PEPPER`: a long, private random value
- Environment variable `BAYFLOW_DATABASE`: `/var/data/malika.sqlite3` when a persistent disk
  is mounted at `/var/data`

The host's public service URL is the **Deployment link**. Do not use `localhost:8000` there.
SQLite needs persistent storage so customer and booking data survive restarts. Render's current
documentation says persistent disks are available on paid services; check the host's current
plan and charges before creating one. A managed PostgreSQL database is a better long-term option
for official multi-user use, but this demo currently uses SQLite.

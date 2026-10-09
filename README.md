# Daily Task Planner

A Flask task planner with user accounts, per-user tasks, PostgreSQL support, password recovery, and light/dark themes.

## Deploy on Render

### 1. Push the project to GitHub

Create a GitHub repository for the project and push the app files. Keep `.env`, `venv/`, and `tasks.db` out of Git; they are listed in `.gitignore`.

### 2. Create the Render service

In Render, choose **New +** > **Blueprint**, connect the GitHub repository, and select this project. Render reads `render.yaml` and creates the web service. The service runs with Gunicorn and checks `/health`.

### 3. Set the database connection string

There are two ways to add `DATABASE_URL`:

- During Blueprint setup, Render prompts for the value marked `sync: false` in `render.yaml`.
- After the service exists, open the service in the Render Dashboard, select **Environment** in the left menu, then add an environment variable:
  - **Key:** `DATABASE_URL`
  - **Value:** your new Neon PostgreSQL connection string

To get the connection string from Neon, open your Neon project, choose **Connect**, select the database and role, then copy the connection string. Use the newly generated password. Keep the full URL private; do not add it to GitHub, `render.yaml`, or this README.

Save the environment changes and redeploy/restart the service if Render does not do so automatically.

### 4. Set the remaining environment variables

The Blueprint automatically generates `SECRET_KEY`. Set `PASSWORD_RESET_CODE` in the same Render **Environment** page to a private value used by the forgot-password flow. Treat it as a secret and do not commit it.

## Run locally

Use Python 3.10 or newer. From the project directory, create and activate a virtual environment, then install the dependencies:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a local `.env` file with your own values:

```dotenv
DATABASE_URL=your-Neon-connection-string
SECRET_KEY=replace-with-a-long-random-secret
PASSWORD_RESET_CODE=replace-with-a-private-reset-code
```

Then start the Flask development server:

```powershell
python -m flask --app app run --debug
```

The local `.env` is ignored by Git. Do not paste credentials into source files or commit them.

## Offline behavior

If PostgreSQL cannot be reached, the app displays a temporary database-unavailable page rather than silently switching to a separate SQLite database. The `/health` endpoint reports whether the web process is running without requiring the database to be available.

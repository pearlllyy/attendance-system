## Using Linux

- Set up Xampp, install xampp and run:
    `sudo /opt/lampp/lampp start` to start and `sudo /opt/lampp/lampp stop` to stop

- Install requirements: 
    `pip install -r requirements.txt`

- If not working, set up virtual environment first: 
    `python3 -m venv venv`

- then to activate the virtual environment:
    `source venv/bin/activate`      - if using bash, 
    `source venv/bin/activate.fish`  - if using fish

- to deactivate:
    `deactivate`

- then install the requirements.

- If using firewall, set profile to trusted or add 5000 tcp port to your firewall

- to run, just simply execute 
    `python app.py`

**Note:** *Dependencies must be updated at all times:* `pip install --upgrade pip`

## Using Podman

- Make sure Podman is installed and available in your terminal.

- Use `compose.yaml` to start the app and database together. Do not build only the `Containerfile`, because that starts the Flask app without the MariaDB service.

- Start the full system with:
    `podman compose up --build`

- If you want it to run in the background, use:
    `podman compose up -d --build`

- To stop the system, use:
    `podman compose down`

- To stop the system and remove the database volume, use:
    `podman compose down -v`

- Open the app in your browser at:
    `https://localhost:5000`

- The app uses a self-signed HTTPS certificate, so your browser will warn you the first time. You can safely continue for local use.

- The database runs inside the Podman stack, so you do not need to start XAMPP for Podman deployment.

- On first run, Podman will also start the MariaDB container and initialize the database from `attendance-db.sql`.

- If `.env` does not exist yet, the container will create it automatically on first boot and generate a `SECRET_KEY` for you.

- The container also writes `MYSQL_HOST=db` into `.env` so the Flask app connects to the MariaDB service inside Podman instead of `localhost`.

- If the admin password is still empty in `.env`, the app will let you set it during the first admin login and save it back to `.env`.

- If you want to reset everything, remove the containers and the database volume, then start again:
    `podman compose down -v`
    `podman compose up --build`

## Using Podman on Windows

- Install Podman for Windows first. Podman on Windows uses WSL2 in the background, so WSL2 must be available on the machine.

- Start the system by double-clicking `launch-windows.bat`.

- To stop the system, double-click `stop-windows.bat`.

- Stopping removes the running containers but keeps the database volume, so your saved data remains for the next launch.

- Open the app in your browser at:
    `https://localhost:5000`

- The browser will warn you about the self-signed certificate the first time. You can continue for local use.

- The database runs inside Podman, so XAMPP is not needed for the Windows Podman setup.

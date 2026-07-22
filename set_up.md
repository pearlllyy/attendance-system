## Using Linux

- If not working, set up virtual environment first: 
    `python3 -m venv venv`

- then to activate the virtual environment:
    `source venv/bin/activate`      - if using bash, 
    `source venv/bin/activate.fish`  - if using fish

- to deactivate:
    `deactivate`

- then install the requirements.

- Install requirements: 
    `pip install -r requirements.txt`

- Set up Xampp, install xampp and run:
    `sudo /opt/lampp/lampp start` to start and `sudo /opt/lampp/lampp stop` to stop

- Create a `.env` file in the project root before running the app. Use this as a starting point:

```env
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DB=attendance_db
MYSQL_PORT=3306
SECRET_KEY=replace_with_a_random_secret
ADMIN_PASSWORD=
```

- You can generate a strong `SECRET_KEY` with:
    `python3 -c "import secrets; print(secrets.token_hex(32))"`

- If you want to change the admin password later, the app will update `ADMIN_PASSWORD` in this same file.

- If using firewall, set profile to trusted or add 5000 tcp port to your firewall

- to run, just simply execute 
    `python app.py`

**Note:** *Dependencies must be updated at all times:* `pip install --upgrade pip`
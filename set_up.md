Set up Xampp, install xampp and run:
    `sudo /opt/lampp/lampp start` to start and `sudo /opt/lampp/lampp stop` to stop

Install requirements: 
    `pip install -r requirements.txt`

Dependencies must be updated at all times: `pip install --upgrade pip`

If not working, set up virtual environment first: 
    `python3 -m venv venv`

then to activate the virtual environment:
    `source venv/bin/activate`      - if using bash, 
    `source venv/bin/activate.fish`  - if using fish

to deactivate:
    `deactivate`

If using firewall, either set profile to trusted or add 5000 port to your firewall

then install the requirements.
to run, just simply execute 
    `python app.py`
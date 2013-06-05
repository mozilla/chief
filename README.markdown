# Description

Chief is a simple web interface to assist in the deployment of web applications.

# Installation

1. git clone git://github.com/jbalogh/chief.git; cd chief
2. cp settings.py.dist settings.py
3. Fill in settings. The "script" will be run in 3 stages:
    1. /usr/bin/commander $script pre_update
    2. /usr/bin/commander $script update
    3. /usr/bin/commander $script deploy
4. Hook up chief.app to mod\_wsgi, gunicorn, etc.

# Requirements

* [Commander](https://github.com/oremj/commander)

# Making an RPM

1. Install [fpm](https://github.com/jordansissel/fpm/wiki)
2. Use fpm like the following example:
`sudo fpm -s dir -t rpm -n "chief" -v 0.1.2 --url "http://github.com/mozilla/chief/" --provides chief -a all --description "Chief is a simple web interface to assist in the deployment of web applications." --maintainer "infra-webops@mozilla.com" -d gunicorn -d python26-redis -d Flask -d python-werkzeug -d python-wtforms -d Jinja2 --prefix "/var/www/chief" --exclude ".git*" /path/to/chief/`

# Change Log

* v0.1.3 - adds support for history pagination, support for arbitrary
  task runners, and some notification support.
  Thanks @oremj, @cturra, and @willkg
* v0.1.2.1 - fix for /chief/ not including a line break, fixes #5
* v0.1.2 - adds proper index page for /chief/, fixes #3
* v0.1.1 - adds a logs directory, fixes #2
* v0.1   - tagged to make an rpm for deployments, by @solarce, fixes #1

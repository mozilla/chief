import json
import os
import re
import subprocess
import time

import redis as redislib
from flask import Flask, Response, abort, request, render_template

import settings
from forms import DeployForm, LoadtestForm


app = Flask(__name__)

os.environ['PYTHONUNBUFFERED'] = 'go time'


def do_update(app_name, app_settings, webapp_ref, who):
    deploy = app_settings['script']
    log_dir = os.path.join(settings.OUTPUT_DIR, app_name)
    timestamp = int(time.time())
    datetime = time.strftime("%b %d %Y %H:%M:%S", time.localtime())
    if not os.path.isdir(log_dir):
        os.mkdir(log_dir)

    log_name = "%s.%s" % (re.sub('[^A-z0-9_-]', '.', webapp_ref), timestamp)
    log_file = os.path.join(log_dir, log_name)

    def run(task, output):
        subprocess.check_call(['commander', deploy, task],
                              stdout=output, stderr=output)

    def pub(event):
        redis = redislib.Redis(**settings.REDIS_BACKENDS['master'])
        d = {'event': event, 'ref': webapp_ref, 'who': who,
             'logname': log_name}
        redis.publish(app_settings['pubsub_channel'], json.dumps(d))

    def history(status):
        redis = redislib.Redis(**settings.REDIS_BACKENDS['master'])
        d = {'timestamp':timestamp, 'datetime': datetime, 
             'status': status, 'user': who, 'ref': webapp_ref,
             'log_name': log_name}
        key = "%s:%s" % (app_name, timestamp)
        redis.hmset(key, d)

    try:
        output = open(log_file, 'a')

        pub('BEGIN')
        yield 'Updating! revision: %s\n' % webapp_ref

        run('pre_update:%s' % webapp_ref, output)
        pub('PUSH')
        yield 'We have the new code!\n'

        run('update', output)
        pub('UPDATE')
        yield "Code has been updated locally!\n"

        run('deploy', output)
        pub('DONE')
        history('Success')
        yield 'All done!'
    except:
        pub('FAIL')
        history('Fail')
        raise

def get_history(app_name, app_settings):
    redis = redislib.Redis(**settings.REDIS_BACKENDS['master'])
    results = []
    key_prefix = "%s:*" % app_name
    for history in redis.keys(key_prefix):
        results.append(redis.hgetall(history))
    return sorted(results, key=lambda k: k['timestamp'], reverse=True)

def do_loadtest(app_name, app_settings, repo):
    log_dir = os.path.join(settings.OUTPUT_DIR, app_name)
    log_file = os.path.join(log_dir, 'loadtest')
    deploy = app_settings['script']

    yield 'Submitting loadtest: %s\n'  % repo
    try:
        output = open(log_file, 'w')
        subprocess.check_call(['commander', deploy, 
                               'loadtest:%s' % repo], stdout=output, 
                              stderr=output)
        yield 'Done!'
    except:
        yield 'Error, check logs!'
        raise

@app.route("/")
def hello():
    webapps = settings.WEBAPPS
    return render_template("webapp_list.html", web_apps = webapps)

@app.route("/<webapp>", methods=['GET', 'POST'])
def index(webapp):
    if webapp not in settings.WEBAPPS.keys():
        abort(404)
    else:
        app_settings = settings.WEBAPPS[webapp]

    errors = []
    form = DeployForm(request.form)
    if request.method == 'POST' and form.validate():
        if form.password.data == app_settings['password']:
            return Response(do_update(webapp, app_settings,
                                      form.ref.data, form.who.data),
                            direct_passthrough=True,
                            mimetype='text/plain')
        else:
            errors.append("Incorrect password")

    return render_template("index.html", app_name=webapp,
                           form=form, errors=errors)

@app.route("/<webapp>/history", methods=['GET'])
def history(webapp):
    if webapp not in settings.WEBAPPS.keys():
        abort(404)
    else:
        app_settings = settings.WEBAPPS[webapp]
    results = get_history(webapp, app_settings)
    return render_template("history.html", app_name=webapp,
                           results=results)

@app.route("/<webapp>/loadtest", methods=['GET', 'POST'])
def loadtest(webapp):
    if webapp not in settings.WEBAPPS.keys():
        abort(404)
    else:
        app_settings = settings.WEBAPPS[webapp]

    errors = []
    form = LoadtestForm(request.form)
    if request.method == 'POST' and form.validate():
        return Response(do_loadtest(webapp, app_settings,
                                      form.repo.data),
                            direct_passthrough=True,
                            mimetype='text/plain')

    return render_template("loadtest.html", app_name=webapp,
                           form=form, errors=errors)

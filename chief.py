import json
import os
import re
import subprocess
import time
import platform

import redis as redislib
from flask import Flask, Response, abort, request, render_template

import settings
from forms import DeployForm, LoadtestForm


app = Flask(__name__)

os.environ['PYTHONUNBUFFERED'] = 'go time'
servername = platform.node()


def fix_settings(app_settings):
    script = app_settings.get('script', None)

    if script:
        app_settings = app_settings.copy()
        app_settings['pre_update'] = ['commander', script, 'pre_update:{ref}']
        app_settings['update'] = ['commander', script, 'update']
        app_settings['deploy'] = ['commander', script, 'deploy']

    return app_settings


def notify(msg):
    for notifier in getattr(settings, 'NOTIFIERS', []):
        notifier(msg)
    return bytes(msg)


def do_update(app_name, app_settings, webapp_ref, who):
    log_dir = os.path.join(settings.OUTPUT_DIR, app_name)
    timestamp = int(time.time())
    datetime = time.strftime("%b %d %Y %H:%M:%S", time.localtime())
    if not os.path.isdir(log_dir):
        os.mkdir(log_dir)

    log_name = "%s.%s" % (re.sub('[^A-z0-9_-]', '.', webapp_ref), timestamp)
    log_file = os.path.join(log_dir, log_name)

    def prefix_notify(msg):
        notify('%s:%s %s' % (app_name, webapp_ref[:12], msg))
        return bytes(msg)

    def run(task, output):
        subprocess.check_call(task,
                              stdout=output, stderr=output)

    def pub(event):
        redis = redislib.Redis(**settings.REDIS_BACKENDS['master'])
        d = {'event': event, 'ref': webapp_ref, 'who': who,
             'logname': log_name}
        redis.publish(app_settings['pubsub_channel'], json.dumps(d))

    def history(status):
        redis = redislib.Redis(**settings.REDIS_BACKENDS['master'])
        d = {'timestamp': timestamp, 'datetime': datetime,
             'status': status, 'user': who, 'ref': webapp_ref,
             'log_name': log_name}
        key = "%s:%s" % (app_name, timestamp)
        redis.hmset(key, d)

    try:
        output = open(log_file, 'a')

        pub('BEGIN')
        yield prefix_notify('%s is pushing %s - %s\n' % (who, app_name, webapp_ref))

        if getattr(settings, 'LOG_ROOT', None):
            yield prefix_notify('%s/%s/logs/%s\n' % (settings.LOG_ROOT,
                                                     app_name, log_name))

        pre_update_head = app_settings['pre_update'][:-1]
        pre_update_tail = [
            app_settings['pre_update'][-1].format(ref=webapp_ref)]
        run(pre_update_head + pre_update_tail, output)

        pub('PUSH')
        yield prefix_notify('We have the new code!\n')
        yield prefix_notify('Running update tasks.\n')

        run(app_settings['update'], output)

        pub('UPDATE')
        yield prefix_notify('Update tasks complete.\n')
        yield prefix_notify('Deploying to webheads.\n')

        run(app_settings['deploy'], output)

        pub('DONE')
        changelog(app_name)
        history('Success')
        yield prefix_notify('Push complete!\n')

    except:
        pub('FAIL')
        history('Fail')
        yield prefix_notify('Something terrible has happened!\n')
        raise

def changelog(app_name):
    import requests
    description = os.uname()[1] + "; Chief: " + app_name
    payload = {"criticality": 1, "unix_timestamp": int(time.time()), "category": "deploy", "description": description}
    url = 'https://changelog.paas.allizom.org/api/events'
    headers = {'content-type': 'application/json'}
    r = requests.post(url, data=json.dumps(payload), headers=headers)

def get_history(app_name, app_settings):
    settings.REDIS_BACKENDS['master']['decode_responses'] = True
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

    yield 'Submitting loadtest: %s\n' % repo
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
    return render_template("webapp_list.html", web_apps=webapps,
                           server_name=servername)


@app.route("/<webapp>", methods=['GET', 'POST'])
def index(webapp):
    if webapp not in settings.WEBAPPS.keys():
        abort(404)
    else:
        app_settings = fix_settings(settings.WEBAPPS[webapp])

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

    # TODO: This pages results poorly by pulling *all* the results
    # back then slicing the returned list. It'd be better to pull just
    # the results we were going to show.
    page = int(request.args.get('page', 0))
    results = get_history(webapp, app_settings)
    results = results[page * 50:(page + 1) * 50]

    return render_template("history.html", app_name=webapp,
                           page=page,
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

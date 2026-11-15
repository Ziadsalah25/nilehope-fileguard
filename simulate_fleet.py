"""Optional synthetic lab client. Uses enrollment API; never rewrites the database."""
import json
import os
import time
import urllib.request
from pathlib import Path

SERVER = os.environ.get('SIMULATOR_SERVER_URL', 'http://127.0.0.1:5000').rstrip('/')
TOKEN = os.environ.get('SIMULATOR_ENROLL_TOKEN', '')
KEY_FILE = Path('simulated_keys.json')
HOSTS = ('SIM-PC01', 'SIM-PC02', 'SIM-FILE01')


def post(path, payload, hostname=None, key=None):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers.update({'X-Device': hostname, 'X-Api-Key': key})
    req = urllib.request.Request(SERVER + '/api/agent/' + path,
                                 data=json.dumps(payload).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def main():
    if os.environ.get('FC_ENV') == 'production' or not TOKEN:
        raise SystemExit('Lab only. Set SIMULATOR_ENROLL_TOKEN and do not run against production.')
    keys = json.loads(KEY_FILE.read_text()) if KEY_FILE.exists() else {}
    for host in HOSTS:
        if host not in keys:
            keys[host] = post('enroll', {'hostname': host, 'token': TOKEN, 'ring': 'pilot'})['key']
            KEY_FILE.write_text(json.dumps(keys))
            KEY_FILE.chmod(0o600)
    print('Synthetic lab devices active. No Windows actions are executed.')
    while True:
        for host in HOSTS:
            response = post('heartbeat', {'win_user': 'LAB\\synthetic', 'department': 'Simulation',
                                          'agent_version': 'SIM-1.2'}, host, keys[host])
            if response.get('command'):
                post('command-result', {'command_id': response['command']['id'],
                                       'output': '[SIMULATED] No actual Windows action executed.',
                                       'success': True}, host, keys[host])
        time.sleep(5)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass

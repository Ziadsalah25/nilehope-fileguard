import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from app import audit, create_app, db, services


def login(client):
    assert client.get('/login').status_code == 200
    with client.session_transaction() as session:
        csrf = session['csrf']
    response = client.post('/login', data={'username': 'admin', 'password': 'TestPassword123!', 'csrf': csrf})
    assert response.status_code == 302
    with client.session_transaction() as session:
        return session['csrf']


def enroll(client, name='FILE01'):
    response = client.post('/api/agent/enroll', json={'hostname': name, 'ring': 'pilot', 'token': 'test-enrollment-token'})
    assert response.status_code == 200
    return {'X-Device': name, 'X-Api-Key': response.json['key']}


def add_share(app, path=r'\\FILE01\Finance'):
    with app.app_context():
        db.q('INSERT INTO folders (path) VALUES (?)', (path,))


def test_login_and_all_pages(client):
    assert client.get('/').status_code == 302
    login(client)
    for path in ('/', '/partials/overview', '/approvals', '/devices', '/settings', '/audit', '/search?q=test'):
        response = client.get(path)
        assert response.status_code == 200, (path, response.data)
    assert client.get('/static/hospital_logo.jpg').status_code == 200
    assert client.get('/healthz').json == {'ok': True}


def test_csrf_required_and_settings_persist(app, client):
    token = login(client)
    assert client.post('/settings/save', data={}).status_code == 400
    assert client.post('/settings/save', data={'csrf': token, 'approval_minutes': '45', 'pol_usb': 'on'}).status_code == 302
    with app.app_context():
        assert services.setting('approval_minutes') == '45'
        assert services.setting('pol_usb') == '1'
        assert services.setting('pol_cloud') == '0'
        assert audit.verify() == (True, None)


def test_login_lockout(client):
    client.get('/login')
    with client.session_transaction() as session:
        token = session['csrf']
    for _ in range(5):
        client.post('/login', data={'username': 'admin', 'password': 'wrong', 'csrf': token})
    response = client.post('/login', data={'username': 'admin', 'password': 'TestPassword123!', 'csrf': token})
    assert b'Too many failed attempts' in response.data


def test_monitoring_gates(app, client):
    assert client.get('/request').status_code == 403
    with app.app_context():
        rid = services.create_request('tester', 'Delete', r'\\FILE01\Finance\demo.txt', 'Test request')
        with pytest.raises(ValueError, match='disabled'):
            services.decide(rid, 'admin', True)
        with pytest.raises(ValueError, match='disabled'):
            services.queue_device_command(1, 'lock_usb')
        assert db.q('SELECT status FROM requests WHERE id=?', (rid,), one=True)['status'] == 'pending'


def test_approval_overlap_and_expiry(app):
    app.config['ENABLE_DIRECTORY_WRITES'] = True
    with app.app_context():
        first = services.create_request('tester', 'Delete', r'\\FILE01\Finance\one', 'First test')
        second = services.create_request('tester', 'Delete', r'\\FILE01\Finance\two', 'Second test')
        services.decide(first, 'admin', True)
        services.decide(second, 'admin', True)
        adapter = services.directory()
        services.revoke(first, 'admin')
        assert adapter.has('tester', services.group_for('Delete'))
        expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime(audit.FMT)
        db.q('UPDATE requests SET expires_at=? WHERE id=?', (expired, second))
        services.expire_grants()
        assert not adapter.has('tester', services.group_for('Delete'))
        assert db.q('SELECT status FROM requests WHERE id=?', (second,), one=True)['status'] == 'expired'
        assert audit.verify() == (True, None)


def test_commands_owned_idempotent_and_allowlisted(app, client):
    app.config['ENABLE_REMOTE_COMMANDS'] = True
    first = enroll(client)
    second = enroll(client, 'FILE02')
    with app.app_context():
        device_id = db.q('SELECT id FROM devices WHERE hostname=?', ('FILE01',), one=True)['id']
        with pytest.raises(ValueError, match='Unsupported'):
            services.queue_device_command(device_id, 'arbitrary_shell')
        services.queue_device_command(device_id, 'restore_usb', 'named-admin')
    command = client.post('/api/agent/heartbeat', headers=first, json={}).json['command']
    assert command['command'] == 'restore_usb'
    assert client.post('/api/agent/heartbeat', headers=first, json={}).json['command'] is None
    payload = {'command_id': command['id'], 'output': 'No prior USB state', 'success': False}
    assert client.post('/api/agent/command-result', headers=second, json=payload).status_code == 409
    assert client.post('/api/agent/command-result', headers=first, json=payload).status_code == 200
    assert client.post('/api/agent/command-result', headers=first, json=payload).status_code == 200
    with app.app_context():
        cmd = db.q('SELECT * FROM device_commands WHERE id=?', (command['id'],), one=True)
        assert cmd['status'] == 'failed'
        assert db.q("SELECT actor FROM audit WHERE action='device.command'", one=True)['actor'] == 'named-admin'


def test_concurrent_command_claim(app, client):
    app.config['ENABLE_REMOTE_COMMANDS'] = True
    enroll(client)
    with app.app_context():
        did = db.q('SELECT id FROM devices', one=True)['id']
        services.queue_device_command(did, 'collect_logs')
    def claim(_):
        with app.app_context():
            return services.get_pending_command(did)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(claim, range(4)))
    assert sum(result is not None for result in results) == 1


def test_enrollment_and_api_key_protection(app, client):
    headers = enroll(client)
    with app.app_context():
        assert db.q('SELECT api_key_hash FROM devices', one=True)['api_key_hash'] == hashlib.sha256(headers['X-Api-Key'].encode()).hexdigest()
    assert client.post('/api/agent/heartbeat', headers={'X-Device': 'FILE01', 'X-Api-Key': 'wrong'}, json={}).status_code == 401
    assert client.post('/api/agent/enroll', json={'token': 'wrong'}).status_code == 403
    assert client.post('/api/agent/enroll', json={'hostname': 'FILE01', 'ring': 'pilot', 'token': 'test-enrollment-token'}).status_code == 409
    app.config['ENROLLMENT_ENABLED'] = False
    assert client.post('/api/agent/enroll', json={}).status_code == 403


@pytest.mark.parametrize('payload', [[], 'text', 42, None])
def test_malformed_agent_payload(client, payload):
    headers = enroll(client)
    assert client.post('/api/agent/heartbeat', headers=headers, json=payload).status_code == 400


def test_share_config_event_scope_and_probe(app, client):
    headers = enroll(client)
    other = enroll(client, 'FILE02')
    add_share(app, r'\\FILE01.hospital.internal\Finance')
    assert client.get('/api/agent/config', headers=headers).json['folders'] == [r'\\FILE01.hospital.internal\Finance']
    assert client.get('/api/agent/config', headers=other).json['folders'] == []
    response = client.post('/api/agent/events', headers=headers, json={'events': [
        {'file': r'\\FILE01\Finance\demo.txt', 'result': 'blocked'},
        {'file': r'\\FILE01\FinanceOther\demo.txt', 'result': 'allowed'},
        {'file': r'\\FILE02\Finance\demo.txt', 'result': 'allowed'},
    ]})
    assert response.json == {'stored': 1}
    assert client.post('/api/agent/events', headers=headers, json={'events': [42]}).status_code == 400
    payload = {'folder': r'\\FILE01.hospital.internal\Finance', 'result': 'review_required'}
    assert client.post('/api/agent/probe', headers=other, json=payload).status_code == 400
    assert client.post('/api/agent/probe', headers=headers, json=payload).status_code == 200
    with app.app_context():
        assert services.layers()[0]['ok'] is False


def test_share_import_validated_before_writing(app, tmp_path):
    path = tmp_path / 'shares.csv'
    path.write_text('Path\n"\\\\FILE01\\Finance"\n"\\\\FILE01\\Finance"\n', encoding='utf-8')
    runner = app.test_cli_runner()
    result = runner.invoke(args=['import-shares', str(path)])
    assert result.exit_code == 0, result.output
    assert '1 new monitoring' in result.output
    path.write_text('Path\n"\\\\FILE01\\Other"\n"\\\\FILE01\\*"\n', encoding='utf-8')
    assert runner.invoke(args=['import-shares', str(path)]).exit_code != 0
    with app.app_context():
        assert db.q('SELECT COUNT(*) AS c FROM folders', one=True)['c'] == 1


def test_audit_tampering_detected(app):
    with app.app_context():
        audit.log('admin', 'test.first')
        audit.log('admin', 'test.second')
        assert audit.verify() == (True, None)
        db.q("UPDATE audit SET target='changed' WHERE action='test.first'")
        assert audit.verify()[0] is False


def test_transaction_rolls_back(app):
    with app.app_context():
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.q('INSERT INTO folders (path) VALUES (?)', (r'\\FILE01\Rollback',))
                raise RuntimeError('test rollback')
        assert db.q('SELECT COUNT(*) AS c FROM folders', one=True)['c'] == 0


def test_database_outage_does_not_fallback(app, client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app.config['DATABASE_URL'] = 'postgresql://test:test@127.0.0.1:1/unreachable'
    with app.app_context():
        with pytest.raises(Exception):
            db.get_db()
    assert not (tmp_path / 'file_control.db').exists()
    assert client.get('/healthz').status_code == 503


def test_schema_failure_is_visible(app, monkeypatch):
    with app.app_context():
        def fail(*args, **kwargs):
            raise RuntimeError('invalid schema')
        monkeypatch.setattr(db, 'q', fail)
        with pytest.raises(RuntimeError, match='invalid schema'):
            db.init_schema()


def test_production_secrets_required(monkeypatch):
    monkeypatch.setenv('FC_ENV', 'production')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app()


def test_production_cannot_use_mock_approvals(monkeypatch):
    monkeypatch.setenv('FC_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'a' * 64)
    monkeypatch.setenv('ENROLL_TOKEN', 'b' * 64)
    monkeypatch.delenv('LDAP_URI', raising=False)
    with pytest.raises(RuntimeError, match='LDAPS'):
        create_app({'ENABLE_DIRECTORY_WRITES': True})

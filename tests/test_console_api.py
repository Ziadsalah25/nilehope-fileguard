import csv
import io

import pytest
from app import audit, create_app, db, services


def authenticated(client):
    session = client.get('/api/console/session').json
    result = client.post('/api/console/login', json={'username':'admin','password':'TestPassword123!'},
                         headers={'X-CSRF-Token': session['csrf']})
    assert result.status_code == 200
    return {'X-CSRF-Token': result.json['csrf']}


def test_session_authentication_csrf_and_logout(client):
    assert client.get('/api/console/session').json['user'] is None
    assert client.get('/api/console/devices').status_code == 401
    assert client.post('/api/console/login', json={}).status_code == 400
    headers = authenticated(client)
    assert client.get('/api/console/session').json['user'] == 'admin'
    assert client.get('/api/console/session').headers['Cache-Control'] == 'no-store'
    assert client.delete('/api/console/shares/1').status_code == 400
    assert client.post('/api/console/logout', json={}, headers=headers).status_code == 200
    assert client.get('/api/console/overview').status_code == 401


def test_console_devices_exclude_credentials(app, client):
    authenticated(client)
    with app.app_context():
        services.enroll_device('SIM-DEVICE', 'pilot')
    response = client.get('/api/console/devices')
    assert response.status_code == 200
    assert response.json['items'][0]['hostname'] == 'SIM-DEVICE'
    assert 'api_key_hash' not in response.json['items'][0]
    assert b'password_hash' not in response.data


def test_share_add_duplicate_remove_and_csrf(client):
    headers = authenticated(client)
    assert client.post('/api/console/shares', json={'path':r'\\FILE01\Finance'}, headers=headers).status_code == 201
    assert client.post('/api/console/shares', json={'path':r'\\FILE01\Finance'}, headers=headers).status_code == 409
    assert client.post('/api/console/shares', json={'path':r'\\FILE01\*'}, headers=headers).status_code == 400
    folder = client.get('/api/console/shares').json['items'][0]
    assert client.delete(f"/api/console/shares/{folder['id']}", headers=headers).status_code == 200
    assert client.get('/api/console/shares').json['items'] == []


def test_activity_filter_pagination_and_export_formula_safety(app, client):
    authenticated(client)
    with app.app_context():
        for i in range(27):
            db.q('INSERT INTO file_events (ts,device,win_user,action,file,result) VALUES (?,?,?,?,?,?)',
                 (audit.now(), 'SIM-FILE', '=SUM(A1:A2)', 'Delete access check', fr'\\SIM-FILE\Training\file{i}.txt',
                  'blocked' if i % 2 else 'allowed'))
    first = client.get('/api/console/events').json
    assert first['total'] == 27 and len(first['items']) == 25
    assert len(client.get('/api/console/events?page=2').json['items']) == 2
    assert client.get('/api/console/events?result=blocked').json['total'] == 13
    assert client.get('/api/console/events?q=missing').json['total'] == 0
    response = client.get('/api/console/events/export')
    rows = list(csv.DictReader(io.StringIO(response.data.decode())))
    assert len(rows) == 27
    assert rows[0]['win_user'].startswith("'=SUM")


def test_runtime_inspection_schema_and_preferences(client):
    headers = authenticated(client)
    system = client.get('/api/console/system').json
    assert system['database']['connected'] is True
    assert len(system['database']['tables']) == 13
    assert {'recovery_agents', 'upload_requests'} <= {row['name'] for row in system['database']['tables']}
    assert 'recovery_events' in {row['name'] for row in system['database']['tables']}
    assert 'device_ip_history' in {row['name'] for row in system['database']['tables']}
    assert system['configuration']['monitoring_only'] is True
    assert system['worker']['online'] is False
    assert client.get('/api/console/system/schema').status_code == 200
    assert b'CREATE TABLE IF NOT EXISTS devices' in client.get('/api/console/system/schema').data
    assert client.post('/api/console/settings', json={'approval_minutes':45}, headers=headers).status_code == 200
    assert client.get('/api/console/settings').json['values']['approval_minutes'] == '45'
    assert client.post('/api/console/settings', json={'approval_minutes':999}, headers=headers).status_code == 400


def test_requests_and_command_gate_remain_monitoring_only(app, client):
    headers = authenticated(client)
    response = client.post('/api/console/requests', json={
        'requester':'training-user','action':'Delete','path':r'\\FILE01\E\demo.txt','reason':'Synthetic integration test'}, headers=headers)
    assert response.status_code == 201
    request_id = response.json['id']
    assert client.post(f'/api/console/requests/{request_id}/approve', json={}, headers=headers).status_code == 400
    assert client.post('/api/console/devices/1/commands', json={'command':'lock_usb'}, headers=headers).status_code == 400
    with app.app_context():
        assert db.q('SELECT status FROM requests WHERE id=?', (request_id,), one=True)['status'] == 'pending'
    assert client.get('/api/console/audit').json['integrity'] is True


@pytest.mark.parametrize('role,agent_status,console_status', [('console',404,200),('agent',401,404)])
def test_service_role_route_isolation(app, role, agent_status, console_status):
    isolated = create_app({**app.config,'SERVICE_ROLE':role})
    client = isolated.test_client()
    assert client.get('/healthz').status_code == 200
    assert client.get('/api/agent/config').status_code == agent_status
    assert client.get('/api/console/session').status_code == console_status


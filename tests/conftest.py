import os

import pytest
from app import audit, create_app, db
from werkzeug.security import generate_password_hash


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv('FC_ENV', raising=False)
    monkeypatch.delenv('LDAP_URI', raising=False)
    application = create_app({
        'TESTING': True, 'SECRET_KEY': 'test-session-key',
        'DATABASE_URL': os.environ.get('TEST_DATABASE_URL', f'sqlite:///{tmp_path}/test.db'),
        'ENROLL_TOKEN': 'test-enrollment-token', 'SESSION_COOKIE_SECURE': False,
        'ENABLE_DIRECTORY_WRITES': False, 'ENABLE_REMOTE_COMMANDS': False,
        'STAFF_REQUESTS_ENABLED': False,
    })
    with application.app_context():
        db.init_schema()
        for table in ('recovery_events', 'device_commands', 'file_events', 'probes', 'folders', 'requests', 'devices', 'settings', 'audit', 'admins'):
            db.q(f'DELETE FROM {table}')
        db.q('INSERT INTO admins (username,password_hash,created_at) VALUES (?,?,?)',
             ('admin', generate_password_hash('TestPassword123!'), audit.now()))
    return application


@pytest.fixture
def client(app):
    return app.test_client()



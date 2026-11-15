"""Idempotent schema/admin setup. Never resets existing accounts or hospital data."""
import os

from werkzeug.security import generate_password_hash

from . import audit, create_app, db


def main():
    app = create_app()
    with app.app_context():
        db.init_schema()
        user = os.environ.get('BOOTSTRAP_ADMIN_USER', 'admin')
        if not db.q('SELECT id FROM admins WHERE username=?', (user,), one=True):
            password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD', '')
            if len(password) < 12:
                raise RuntimeError('BOOTSTRAP_ADMIN_PASSWORD needs at least 12 characters')
            db.q('INSERT INTO admins (username,password_hash,created_at) VALUES (?,?,?)',
                 (user, generate_password_hash(password), audit.now()))
            audit.log('bootstrap', 'admin.create', user)
        # No network or hospital target is registered by default.
        target = os.environ.get('HOSPITAL_SHARE_PATH', '')
        if target:
            from .shares import valid_share
            if not valid_share(target):
                raise RuntimeError('HOSPITAL_SHARE_PATH must be a valid exact UNC path')
            if not db.q('SELECT id FROM folders WHERE path=?', (target,), one=True):
                db.q('INSERT INTO folders (path) VALUES (?)', (target,))
        print('Schema and console account are ready.', flush=True)


if __name__ == '__main__':
    main()

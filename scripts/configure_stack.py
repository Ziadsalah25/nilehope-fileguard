"""Create local-only test credentials without overwriting an existing environment."""
import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='.env')
args = parser.parse_args()
path = Path(args.output)
if path.exists():
    raise SystemExit(f'{path} already exists; existing configuration was preserved.')
values = {
    'MYSQL_DATABASE': 'nilehope_fileguard', 'MYSQL_USER': 'dlp_app',
    'MYSQL_PASSWORD': secrets.token_hex(24), 'MYSQL_ROOT_PASSWORD': secrets.token_hex(24),
    'SECRET_KEY': secrets.token_hex(32), 'ENROLL_TOKEN': secrets.token_hex(32),
    'BOOTSTRAP_ADMIN_USER': 'admin', 'BOOTSTRAP_ADMIN_PASSWORD': secrets.token_urlsafe(18),
    'FC_ENV': 'testing', 'CONSOLE_ENVIRONMENT': 'test',
    'PUBLIC_CONSOLE_URL': 'http://localhost:8080', 'FRONTEND_PORT': '8080',
    'MYSQL_HOST_PORT': '13306',
}
path.write_text(''.join(f'{k}={v}\n' for k, v in values.items()), encoding='utf-8')
path.chmod(0o600)
print(f'Local test configuration saved to {path}. Read the admin login from this protected file.')
print('Do not upload the file or commit it. HTTPS deployment uses a separate production override.')

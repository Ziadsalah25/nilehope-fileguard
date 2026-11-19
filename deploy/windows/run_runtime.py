"""Start a Windows runtime using its protected configuration file."""
import argparse
import json
import os
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/management"))

parser = argparse.ArgumentParser()
parser.add_argument('config', type=Path)
parser.add_argument('action', choices=('web', 'worker', 'init-db', 'create-admin', 'import-shares'))
parser.add_argument('arguments', nargs='*')
args = parser.parse_args()
with args.config.open(encoding='utf-8-sig') as source:
    os.environ.update({k: str(v) for k, v in json.load(source).items()})

from app import create_app  # noqa: E402

if args.action == 'web':
    certificate = os.environ.get('TLS_CERTIFICATE_FILE')
    private_key = os.environ.get('TLS_PRIVATE_KEY_FILE')
    if bool(certificate) != bool(private_key):
        raise RuntimeError('TLS_CERTIFICATE_FILE and TLS_PRIVATE_KEY_FILE must be configured together')
    if certificate:
        import ssl

        from cheroot import wsgi
        from cheroot.ssl.builtin import BuiltinSSLAdapter

        cert_path = Path(certificate)
        key_path = Path(private_key)
        if not cert_path.is_file() or not key_path.is_file():
            raise RuntimeError('Configured HTTPS certificate or private key is missing')
        address = os.environ.get('TLS_BIND_ADDRESS', '127.0.0.1')
        port = int(os.environ.get('TLS_PORT', '8443'))
        if not 1 <= port <= 65535:
            raise RuntimeError('TLS_PORT must be between 1 and 65535')
        server = wsgi.Server((address, port), create_app(), numthreads=8)
        adapter = BuiltinSSLAdapter(str(cert_path), str(key_path))
        adapter.context.minimum_version = ssl.TLSVersion.TLSv1_2
        server.ssl_adapter = adapter
        server.safe_start()
    else:
        from waitress import serve

        serve(create_app(), host='127.0.0.1', port=8000, threads=8)
elif args.action == 'worker':
    runpy.run_module('app.worker', run_name='__main__')
else:
    app = create_app()
    with app.app_context():
        app.cli.main(args=[args.action, *args.arguments], prog_name='dlp', standalone_mode=True)

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
    from waitress import serve
    serve(create_app(), host='127.0.0.1', port=8000, threads=8)
elif args.action == 'worker':
    runpy.run_module('app.worker', run_name='__main__')
else:
    app = create_app()
    with app.app_context():
        app.cli.main(args=[args.action, *args.arguments], prog_name='dlp', standalone_mode=True)

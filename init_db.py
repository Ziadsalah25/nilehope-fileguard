import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent / "services/management"))
from app import create_app, db
app = create_app()
with app.app_context():
    db.init_schema()
print('Database schema initialized')

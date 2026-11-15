# MySQL Workbench

MySQL is published only on the Docker host's loopback interface.

| Setting | Value |
|---|---|
| Method | Standard TCP/IP |
| Host | `127.0.0.1` on the Docker host |
| Port | `13306` |
| Username/password | Generated locally in `.env` |
| Schema | `nilehope_fileguard` |

```sql
SELECT hostname, os_family, last_seen FROM devices ORDER BY hostname;
SELECT kind, COUNT(*) FROM recovery_events GROUP BY kind;
SELECT ts, relative_path, kind, sha256 FROM recovery_events ORDER BY id DESC LIMIT 100;
```

Workbench on another PC needs an authorized network route or SSH tunnel. The cloud lab does not publish MySQL to the internet. A cloud `localhost` address cannot be opened on your PC to reach this installation.

**System & database** provides service health, row counts, and a SQL schema download without exposing passwords or key hashes.

CREATE TABLE IF NOT EXISTS admins (
  id {PK}, username VARCHAR(64) UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS devices (
  id {PK}, hostname VARCHAR(63) UNIQUE NOT NULL, win_user TEXT, department TEXT, ip TEXT, mac TEXT,
  agent_version TEXT, ring VARCHAR(16) NOT NULL DEFAULT 'pilot', api_key_hash VARCHAR(64) NOT NULL,
  last_seen TEXT, created_at TEXT NOT NULL,
  os_family VARCHAR(16) NOT NULL DEFAULT 'unknown', os_version VARCHAR(160), architecture VARCHAR(32),
  cpu_percent REAL, memory_total_mb BIGINT, memory_used_mb BIGINT, disk_total_mb BIGINT, disk_used_mb BIGINT,
  uptime_seconds BIGINT, telemetry_at TEXT, monitoring_status VARCHAR(20) NOT NULL DEFAULT 'unknown', monitoring_message TEXT);
CREATE TABLE IF NOT EXISTS file_events (
  id {PK}, ts TEXT NOT NULL, win_user TEXT, device TEXT, ip TEXT, action TEXT NOT NULL,
  file TEXT, process TEXT, result TEXT NOT NULL, event_key VARCHAR(64) UNIQUE,
  source_event_id INTEGER, record_id VARCHAR(32), logon_id VARCHAR(32), handle_id VARCHAR(32),
  access_mask VARCHAR(16), share_name VARCHAR(128), client_device VARCHAR(63), client_match VARCHAR(16));
CREATE TABLE IF NOT EXISTS device_ip_history (
  id {PK}, device_id INTEGER NOT NULL, ip VARCHAR(45) NOT NULL,
  seen_from VARCHAR(40) NOT NULL, seen_to VARCHAR(40));
CREATE TABLE IF NOT EXISTS requests (
  id {PK}, requester TEXT NOT NULL, action TEXT NOT NULL, path TEXT NOT NULL, reason TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
  decided_by TEXT, decided_at TEXT, expires_at TEXT, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS audit (
  id {PK}, ts TEXT NOT NULL, actor TEXT, action TEXT NOT NULL, target TEXT NOT NULL,
  outcome TEXT NOT NULL, prev_hash VARCHAR(64) UNIQUE NOT NULL, hash VARCHAR(64) NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key_name VARCHAR(64) PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS folders (id {PK}, path {PATH_TYPE} NOT NULL, state VARCHAR(40) NOT NULL DEFAULT 'Monitored', target_os VARCHAR(16) NOT NULL DEFAULT 'windows', target_host VARCHAR(63) NOT NULL DEFAULT '', UNIQUE(path,target_os,target_host));
CREATE TABLE IF NOT EXISTS probes (id {PK}, ts TEXT NOT NULL, folder TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS device_commands (
  id {PK}, device_id INTEGER NOT NULL, command TEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending',
  output TEXT, created_at TEXT NOT NULL, executed_at TEXT);
CREATE TABLE IF NOT EXISTS recovery_events (
  id {PK}, event_key VARCHAR(64) UNIQUE NOT NULL, ts VARCHAR(40) NOT NULL, device_id INTEGER NOT NULL,
  kind VARCHAR(32) NOT NULL, relative_path VARCHAR(400) NOT NULL, version_id VARCHAR(64),
  sha256 VARCHAR(64), bytes BIGINT, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recovery_agents (
  device_id INTEGER PRIMARY KEY, host_name VARCHAR(63) NOT NULL, mode VARCHAR(16) NOT NULL,
  protected_root VARCHAR(400) NOT NULL, monitoring_status VARCHAR(20) NOT NULL,
  message TEXT NOT NULL, reported_at VARCHAR(40) NOT NULL);
CREATE TABLE IF NOT EXISTS upload_requests (
  id {PK}, storage_key VARCHAR(32) UNIQUE NOT NULL, file_name VARCHAR(255) NOT NULL,
  sha256 VARCHAR(64) NOT NULL, bytes BIGINT NOT NULL, reason TEXT NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending', submitted_by VARCHAR(64) NOT NULL,
  created_at VARCHAR(40) NOT NULL, decided_by VARCHAR(64), decided_at VARCHAR(40));


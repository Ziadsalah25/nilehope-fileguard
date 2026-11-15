-- Read-only queries. Execute after connecting to the hospital MySQL server in Workbench.
SELECT VERSION() AS mysql_version, @@hostname AS server_name, @@port AS server_port, CURRENT_USER() AS connected_account;
SHOW DATABASES LIKE 'nilehope_fileguard';
SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA='nilehope_fileguard' ORDER BY TABLE_NAME;
-- After the application schema is initialized:
-- USE nilehope_fileguard;
-- SELECT hostname, win_user, department, ip, mac, agent_version, ring, last_seen FROM devices ORDER BY hostname;
-- SELECT ts, device, win_user, action, file, result FROM file_events ORDER BY id DESC LIMIT 100;
-- SELECT path, state FROM folders ORDER BY path;
-- SELECT id, device_id, command, status, created_at, executed_at FROM device_commands ORDER BY id DESC LIMIT 50;

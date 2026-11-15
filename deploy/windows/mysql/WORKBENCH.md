# MySQL on EXAMPLE-FILE01; Workbench on your PC

The console test is monitoring-only. Remote commands and directory writes are disabled by default; no USB, SMB session, NTFS or GPO changes are part of the initial connection test.

## Connection layout

- Windows MySQL Server: EXAMPLE-FILE01 / 192.0.2.10, TCP port 3306 (confirm the real server port).
- MySQL Workbench: your PC, Standard TCP/IP connection to 192.0.2.10:3306, using an existing account authorized for that source PC.
- Console: the VM itself, application account connecting to 127.0.0.1:3306.
- Application database: `nilehope_fileguard`, UTF-8 (`utf8mb4`).

Workbench is a client; the MySQL Server service must be installed and running on the VM. Installation status is not established by the supplied hospital-info.json.

## First test: from your PC

```powershell
Test-NetConnection 192.0.2.10 -Port 3306 -InformationLevel Detailed |
    Select-Object ComputerName,RemoteAddress,RemotePort,SourceAddress,TcpTestSucceeded
```

This does not change firewall rules or start/stop services. If TCP succeeds, create a Workbench connection with host 192.0.2.10, port 3306 and your existing MySQL username. Enter its password locally. Execute `inspect.sql` to identify the actual server and any existing application schema. Do not upload database passwords or runtime.json.

For remote Workbench sessions, configure SSL using the MySQL server's trusted CA; a Workbench account can be required to use TLS. A private network TCP test alone does not validate database authentication or TLS.

If TCP fails, inspect the VM's MySQL service, bind/listen address and existing firewall rules. Any new inbound 3306 rule should match the actual Workbench PC source address rather than publishing MySQL externally. No firewall changes are bundled in the connection test.

## Fresh database setup

After identifying the existing database/application, run `create-database.sql` locally as a MySQL administrator, then `schema.mysql.sql` with `nilehope_fileguard` selected. The schema creates nine tables and never inserts invented hospital devices.

Create an application account for local TCP access, such as `dlp_app` at `127.0.0.1`. Give it SELECT, INSERT, UPDATE, DELETE and CREATE on `nilehope_fileguard` only. A separately scoped Workbench account can inspect the database from your PC. Choose passwords locally; none are supplied or collected in this package. Existing accounts or tables are not automatically reset or migrated.

The console connection URL has this form:

```
mysql://dlp_app:URL_ENCODED_PASSWORD@127.0.0.1:3306/nilehope_fileguard
```

Use `urllib.parse.quote(password, safe='')` when constructing it locally. Pass the URL through the protected runtime configuration. It is a credential, not a discovery artifact to upload.

## Tables

| Table | Records |
| --- | --- |
| devices | Agent identity, Windows user, IP/MAC, version, heartbeat time |
| file_events | SMB access-check metadata from registered shares |
| folders | Share paths selected for monitoring |
| probes | ACL observations, not effective-access proof |
| device_commands | Command queue, result and state; dispatch disabled during the test |
| requests | Requested approvals and their decisions |
| audit | Hash-chained administrator/system activity |
| admins | Console administrator names and password hashes |
| settings | Console preferences |

Device rows appear only after real agents enroll. The supplied hospital-info.json describes the VM and shares but is not an enrolled-device inventory. No real hospital database has been connected to or queried from the cloud workspace yet.

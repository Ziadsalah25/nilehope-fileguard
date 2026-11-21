# File Share Event Attribution

## Scope

The Windows file-server agent observes selected, administrator-configured UNC roots. It does not enforce access decisions or modify share permissions, NTFS permissions, auditing policy, or auditing SACLs. Windows Share and NTFS ACLs remain the enforcement point for delete restrictions.

The collector sends metadata only. It does not upload file contents.

## Collected event types

- **5145:** SMB share access checks. Delete-right checks include the server-reported account, client source IP, share-relative path, timestamp, and allow/fail result.
- **4656:** Requests for handles with delete-related rights. Failure events can help identify an NTFS denial when the required File System audit policy and SACL are configured.
- **4663:** Use of audited delete-related rights on a file-system object.
- **4660:** Completed deletion. This event does not contain a path by itself; the agent includes a path only when it can associate the event's handle and logon ID with a previously observed in-scope file-system record.

File-system paths are resolved through Windows share definitions and filtered against the exact configured share roots. Unresolvable or out-of-scope paths are not forwarded. A 5145 allow result represents the SMB share check and does not prove the NTFS access check succeeded.

## Client-device matching

Enrolled clients report current IP addresses at heartbeat time. The management API stores start and end times for each device/IP interval. For a file-server event, it matches the event source IP and event timestamp against those intervals:

- One matching enrolled device is recorded as the client.
- No matching device is labeled `unmatched`.
- Multiple matching devices are labeled `ambiguous`; no hostname is selected.

This is time-aware IP correlation, not cryptographic proof of device identity. NAT, shared addresses, missed heartbeats, or a client without an enrolled agent can prevent a unique match. The Windows account is captured from the server Security event.

## Data and retry handling

Each Windows record is associated with a stable agent event key so a retried batch does not duplicate the same activity. The event record stores the Windows event ID and record ID, user/logon ID, handle ID, access mask, share, file path, event timestamp, source IP, client match, action, and result. The console search and CSV export include the client, server, user, IP, share, and Windows event metadata.

The IP history table is added through an additive database migration. It is indexed by IP and event-time interval for lookup.

## Validation status

The local implementation passed the focused attribution tests (7 passed), the React/TypeScript production build, and Windows PowerShell syntax parsing. The full Python suite reported 62 passed and 2 Windows-host limitations in Linux-agent tests: symlink creation requires a Windows privilege, and a Linux path validation test receives a Windows temporary path. No real Windows Security log, SMB share, MySQL migration, or production server was tested.

Before rollout, validate the collector on a disposable Windows share with scoped success/failure auditing and SACLs. Generate allowed and denied delete attempts, verify 5145 and 4656 semantics, check 4663 rights, and confirm 4660 path correlation. Review event volume and Security log retention. Do not treat the console feed as enforcement or as authoritative until the Windows integration test passes.


# Delivery scope and remaining work

| Area | Implemented | Remaining work |
|---|---|---|
| Console/APIs | React, separate Python roles, MySQL, sessions, audit | Operator/auditor/admin RBAC |
| Monitoring | Windows PowerShell; Linux health and selected folders | Real Windows/hospital enrollment tests |
| Recovery | C# stable copies, SHA-256, safe restore, manifest, loop limits | Windows NTFS and Service validation |
| Reporting | HTTPS/device keys; durable event outbox | Signed installers and secure updates |
| Failure handling | Missing-root pause, corrupt-copy rejection, conflicts | Capacity limits, load, crash/power-loss drills |
| Repository | Separate local lab folder | Hardened external/immutable storage |
| File semantics | Stable create/modify content and file deletion | Rename/move identity, directory recovery, ACL/ADS preservation |
| Policies | Local configuration | Approved central policy, maintenance and retention |
| Production | Not deployed | Non-critical pilot, consistency testing, rollback and sign-off |

Next decisions: retention/version limits and capacity; hardened repository location; first Windows test server and disposable directory; dedicated service identity. Supported Windows audit integration is needed for reliable initiating-user attribution. The service identity is never inferred as the deleting user.

Pre-delete blocking needs a separate supported enforcement design or signed minifilter. Restore tests do not establish delete prevention.

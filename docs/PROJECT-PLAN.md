# NileHope FileGuard

## Product Concept, Architecture & Development Roadmap

**Version:** 1.0\
**Status:** Initial proposal / MVP planning\
**Target:** Windows file servers and SMB shares

## 1. Project vision

Build an internally managed file-protection and recovery solution that
detects file-system activity, preserves recoverable versions, restores
deleted or damaged files according to policy, and provides an audit
trail.

The first objective is reliable recovery in a controlled test
environment. Central management, advanced security controls, and
multi-server support come later.

**Proposed name:** NileHope FileGuard (provisional).

## 2. Important distinction: restore versus prevent

There are two different product behaviors:

-   **Self-healing recovery:** detect a delete event and restore a
    protected copy. The file may disappear briefly before restoration.
-   **True delete prevention:** block the delete operation before it
    completes. This generally requires a Windows file-system minifilter
    driver or another supported enforcement mechanism.

The MVP should implement recovery first. Do not describe post-delete
restoration as guaranteed prevention.

## 3. Main components

### 3.1 FileGuard Agent

A Windows Service installed on each protected file server.

Responsibilities: - Monitor configured local NTFS directories. - Detect
create, delete, rename, move, and modify events. - Capture file
versions. - Restore deleted files when policy permits. - Verify restored
content with hashes. - Queue events if the management server is
unavailable. - Send events and health status to the management server. -
Write local diagnostic and audit logs. - Resume safely after service or
server restart.

Use a dedicated service identity with least privilege.

### 3.2 Management Server

Central responsibilities: - Register and manage agents. - Inventory
protected servers, shares, and folders. - Define and assign protection
policies. - Receive events and health reports. - Manage users and
roles. - Display alerts and recovery history. - Export audit reports. -
Coordinate approved restore operations.

### 3.3 Backup / Version Repository

Stores protected copies separately from the live share.

Design goals: - Keep backups outside protected directories. - Restrict
write and delete access. - Use versioned copies and integrity hashes. -
Apply retention policies. - Prevent ordinary share users from deleting
recovery copies. - Support a separate hardened repository for
production.

A local backup folder is acceptable only for an isolated proof of
concept. It is not adequate protection against ransomware or compromise
of the file server.

### 3.4 Dashboard

Suggested pages: - Overview and health summary. - Protected servers. -
Protected shares and folders. - Policy management. - Recent file
activity. - Deleted and restored files. - Version history. - Alerts and
incidents. - Agent health. - User and role management. - Audit reports
and exports.

## 4. High-level architecture

``` text
             +-----------------------------------+
             |       FileGuard Management        |
             | Dashboard / API / Policies        |
             | Agent Registry / Audit Database   |
             +-----------------+-----------------+
                               |
                     HTTPS authenticated API
                               |
              +----------------+----------------+
              |                                 |
      +-------v--------+                +-------v--------+
      | File Server 01 |                | File Server 02 |
      | FileGuard Agent|                | FileGuard Agent|
      | Event Processor|                | Event Processor|
      | Restore Engine |                | Restore Engine |
      +-------+--------+                +-------+--------+
              |                                 |
       Protected SMB data                Protected SMB data

          Separate protected backup / version repository
```

The agent should continue safe local operation during a temporary
management-server outage.

## 5. File activities and suggested behavior

  -----------------------------------------------------------------------
  Activity                            Suggested behavior
  ----------------------------------- -----------------------------------
  Create                              Register and protect after file is
                                      stable

  Delete                              Restore, quarantine, or alert
                                      according to policy

  Rename                              Record old and new paths

  Move                                Record source and destination

  Modify                              Preserve a previous version

  Replace / overwrite                 Preserve old version before
                                      accepting replacement

  Bulk delete                         Trigger alert and incident workflow

  Bulk modification                   Trigger ransomware-suspicion
                                      analysis

  Permission change                   Record ACL change and alert on
                                      sensitive paths

  Directory deletion                  Detect and recover contents where
                                      supported
  -----------------------------------------------------------------------

The first MVP should focus on create, modify, and delete recovery. Add
rename, move, directory recovery, ACL preservation, and bulk-event
correlation after the basic flow is proven.

## 6. Policy engine

Policies can be assigned per server, share, folder, and optionally file
type or user group.

  -----------------------------------------------------------------------
  Activity                            Example policy
  ----------------------------------- -----------------------------------
  Delete                              Restore automatically and log

  Rename                              Allow and audit

  Move                                Allow within approved scope and
                                      audit

  Modify                              Preserve previous version

  Replace                             Preserve old version

  Bulk delete                         Alert, preserve recovery points,
                                      require IT review

  Admin delete                        Allow only when explicitly
                                      authorized; always audit

  Scheduled cleanup                   Allow only approved paths,
                                      identities, and time windows
  -----------------------------------------------------------------------

Safeguards: - Avoid endless restore loops if a user repeatedly deletes a
file. - Provide authorized maintenance mode and exceptions. - Never
overwrite a newer legitimate file without conflict handling. - Log every
automated and failed restore. - Require approval for destructive
retention actions. - Exclude temporary files and high-churn application
working folders where appropriate.

## 7. Recovery and versioning

Example version history:

``` text
Department\\Finance\\Monthly-Report.xlsx
    Version 1 - initial copy
    Version 2 - edited by user
    Version 3 - edited again
    Version 4 - current version
```

Restore workflow:

``` text
File event detected
       |
Identify path and event
       |
Evaluate policy and context
       |
Find valid protected version
       |
Verify backup hash and metadata
       |
Restore safely or create recovery copy
       |
Verify restored file
       |
Write audit event and notify dashboard
```

If a same-name file already exists, do not blindly overwrite it. Support
a conflict-safe temporary name, alternate recovery folder,
policy-authorized replacement, or administrator approval.

Metadata to consider: - File content, original path, and file name. -
Size and timestamps. - NTFS ACLs and ownership. - Alternate data
streams, if required. - File attributes and hashes.

The MVP may initially preserve content and basic timestamps only. Full
metadata and ACL restoration need dedicated testing.

## 8. Monitoring technology

### MVP: FileSystemWatcher

Use a Windows Service with `FileSystemWatcher` for a controlled proof of
concept.

Advantages: - Straightforward implementation. - Useful for demonstrating
common file events. - Supports rapid development and testing.

Limitations: - Notifications can be lost under high event volume. -
Buffer overflow and service downtime can create gaps. - It is not a
durable audit source. - It does not reliably identify the initiating
user or process by itself. - Delete notifications are generally
post-operation.

### Later: NTFS USN Journal

Evaluate the NTFS USN Change Journal for more resilient change tracking
and reconciliation.

The implementation must handle journal wrap/reset, persist the last
processed USN, reconcile after downtime, and track volume/file
identities. USN records alone should not be treated as a complete
security audit or proof of the responsible user.

### True operation blocking

If the requirement is that users must never be able to delete a file,
investigate a Windows file-system minifilter driver or supported storage
enforcement product. A minifilter is kernel-mode software and brings
substantial development, signing, compatibility, stability, and security
requirements. It is not part of the first MVP.

## 9. Ransomware and bulk-change protection

Potential later capabilities: - Detect unusually high delete or modify
rates. - Detect mass extension changes and suspicious rename patterns. -
Alert on activity across many directories. - Preserve recovery points
before large-scale changes. - Correlate with supported Windows
file-server auditing and EDR telemetry. - Trigger an approved
incident-response workflow.

Do not automatically terminate processes, users, or SMB sessions in the
first release. False positives could disrupt hospital operations. Begin
with alerting, evidence preservation, and administrator-approved
response.

FileGuard complements---not replaces---EDR, immutable/offline backups,
access control, and disaster recovery.

## 10. Audit and reporting

Record, where available: - UTC timestamp and server name. - Share and
full file path. - Event type and policy applied. - User identity and
client computer/source address. - Process identity, only when reliably
collected. - Action taken and restore result. - Backup version
identifier and hashes. - Error details.

Do not infer the initiating user from the Windows Service account.
Reliable attribution may require Windows file-server auditing, SMB
telemetry, or another supported event source.

Suggested reports: - Deleted files and recovery results. - Modified
files and available versions. - Top folders by activity. - Bulk-change
alerts. - Agent health and offline periods. - Failed backup/restore
operations. - Policy changes and administrator actions.

## 11. Security requirements

-   Authenticated, encrypted agent-to-server communication (HTTPS/TLS).
-   Individual agent credentials; securely managed certificates or
    tokens.
-   No hardcoded secrets.
-   Role-based access control (RBAC).
-   Separate operator, auditor, and administrator roles.
-   Audit policy changes and administrative actions.
-   Protect backup storage from ordinary file-share users.
-   Least-privilege service identities.
-   Validate paths and prevent path traversal and reparse-point escape.
-   Protect audit logs and apply retention controls.
-   Back up the management database and configuration.
-   Test restore integrity regularly.

## 12. Suggested technology stack

  Component               Suggested technology
  ----------------------- -------------------------------------
  Agent                   C# / .NET Windows Worker Service
  Initial monitoring      FileSystemWatcher
  Later change tracking   NTFS USN Journal
  Management API          ASP.NET Core
  Dashboard               React or ASP.NET Core UI
  MVP database            SQLite for isolated lab
  Production database     SQL Server or PostgreSQL
  Agent communication     HTTPS REST API; durable queue later
  Packaging               Signed Windows service installer

Choose a supported .NET release and patch level according to the
hospital's lifecycle and security standards.

## 13. Development phases

### Phase 0 --- Requirements and lab design

-   Decide whether the requirement is restore-after-delete or true
    pre-delete blocking.
-   Identify Windows Server version and storage type.
-   Define test folder, backup location, service identity, and test
    accounts.
-   Define retention, exclusions, and expected recovery time.
-   Prepare test cases.

**Exit criteria:** approved lab scope and test plan.

### Phase 1 --- MVP Agent

-   Windows Service.
-   Configurable protected folder.
-   Initial baseline snapshot.
-   Detect create, modify, and delete.
-   Store versioned copies.
-   Restore deleted files in the lab.
-   Local audit log.
-   Basic error handling and service restart behavior.

**Exit criteria:** repeatable lab tests with no data loss.

### Phase 2 --- Reliable recovery

-   Hash verification.
-   Safe restore conflict handling.
-   Metadata and ACL testing.
-   Rename and move tracking.
-   Durable event queue.
-   USN Journal reconciliation.
-   Retention and exclusions.

**Exit criteria:** verified behavior after restart, high event volume,
and interrupted monitoring.

### Phase 3 --- Management Server and Dashboard

-   Agent registration.
-   Protected server/share inventory.
-   Central policies.
-   Recent activity and restore history.
-   Alerts and health status.
-   RBAC and administrator audit.

**Exit criteria:** centrally manage at least two lab file servers.

### Phase 4 --- Advanced security

-   Bulk delete/modify detection.
-   Ransomware-suspicion alerts.
-   Windows audit integration for user attribution.
-   Incident review and approval workflows.
-   Hardened/immutable backup integration.

**Exit criteria:** validated detection and controlled false-positive
testing.

### Phase 5 --- Production readiness

-   High availability and database backup.
-   Signed installer and secure updates.
-   Performance and security testing.
-   Disaster recovery procedures.
-   Monitoring, support, and rollback plan.
-   Pilot on a non-critical share.

**Exit criteria:** formal technical approval and operational sign-off.

## 14. MVP test plan

Use a dedicated test server and disposable data only.

  -----------------------------------------------------------------------
  Test                                Expected result
  ----------------------------------- -----------------------------------
  Create file                         File becomes protected after stable

  Modify file                         Previous version remains
                                      recoverable

  Delete file                         Agent detects and restores
                                      according to policy

  Rename file                         Old and new paths are recorded

  Move file                           Source and destination are recorded

  Rapid multi-file delete             Events are recorded; no claim of
                                      guaranteed blocking

  Stop/restart agent                  Agent resumes; missed-event
                                      reconciliation is a later-phase
                                      requirement

  Backup repository unavailable       Error/alert is recorded; protection
                                      is not falsely reported

  Same-name restore conflict          Safe conflict handling; no silent
                                      overwrite

  Unauthorized backup deletion        Repository controls deny access
                                      where configured
  -----------------------------------------------------------------------

Record test results, timestamps, hashes, and screenshots. Do not approve
production based on a single successful delete test.

## 15. Hospital-specific operational considerations

-   Do not interrupt clinical systems or application-managed storage.
-   Confirm whether applications keep files open or update them
    continuously.
-   Exclude application-managed working, cache, temporary, and database
    files unless explicitly supported.
-   Test PACS/DICOM workflows separately; ordinary file restore is not
    automatically safe for PACS data.
-   Coordinate with HIS/PACS vendors where application consistency is
    involved.
-   Define a maintenance window and rollback plan.
-   Approve backup capacity and retention.
-   Treat audit logs and recovered copies as sensitive hospital
    information.
-   Start with a low-risk departmental share, not PACS repositories, HIS
    databases, or other application-critical paths.

## 16. Limitations of the first prototype

A basic `FileSystemWatcher` plus copy-backup implementation is a
demonstration, not a production-grade protection platform. It does not
guarantee: - Prevention of every delete. - Capture of every event under
heavy load. - Reliable identification of the initiating user. -
Protection if an attacker can delete both live data and local backups. -
Application-consistent recovery. - Full restoration of NTFS ACLs and all
metadata.

These require additional engineering, Windows auditing integration,
protected backup infrastructure, and extensive testing.

## 17. Decisions required before the next implementation step

1.  **Protection behavior:** restore immediately after deletion, or
    block deletion before it happens?
2.  **Initial platform:** which Windows Server version will host the
    test agent?
3.  **Storage:** local NTFS, clustered volume, or NAS over SMB?
4.  **Recovery location:** separate local disk, dedicated backup server,
    or NAS/repository?
5.  **Scope:** one test folder or an entire share?
6.  **User attribution:** must every operation identify the exact domain
    user and client PC?
7.  **Retention:** how many days or versions, and what is the expected
    data volume?

## 18. Recommended immediate next step

Build and validate a lab MVP on a non-production Windows Server: - One
disposable test folder. - One dedicated backup location. - One test
domain user and one administrator. - A small set of sample files. -
Documented create/modify/delete/restore tests.

Proceed to central management and production hardening only after
behavior, integrity, and failure cases are verified.

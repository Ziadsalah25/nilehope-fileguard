# Validation record

## 2026-11-16 manual-pilot and upload module

- Full Python suite: **60 passed** in a disposable Linux container, using SQLite. Ruff passed across backend/tests. Two Linux-specific filesystem checks fail on Windows, so the full suite was run on Linux rather than treating those failures as application regressions.
- C# engine: **10 scenarios passed on Windows**, including a monitoring-to-recovery switch across restart, verified latest-version restoration, corruption rejection, conflict preservation, rate limiting, and unavailable-root handling. The Windows symlink case remains outside these engine scenarios.
- React/TypeScript/Vite production build and the updated Docker builds passed. All five running core services are healthy.
- Live local Docker/MySQL workflow: a pending upload returned 403 for download; an approved file downloaded with matching bytes; a rejected file returned 403. Submission/decision/download audit records were stored. These checks used disposable test submissions visible in the local queue.
- A real foreground C# worker on the local Windows laptop captured two versions, reported monitoring-only deletion without restoration, restarted with explicit recovery enabled, restored the latest contents, and reported its local mode and verified recovery to the Docker console. The temporary worker stopped after validation; its QA device/history remain visible as local test evidence.
- The self-contained win-x64 package built successfully. All new PowerShell scripts parsed successfully, and Windows ACL rule construction was checked. The generated unsigned test launcher was blocked by local application-control policy; managed engine tests ran through the installed .NET runtime. Deployment executables may require organizational signing/allowlisting.
- No recovery Windows service was installed on the real file server, no SMB share/ACL or domain/GPO was changed, and no domain user's physical device was enrolled by these checks. Service-account permissions, certificate trust, and the real SMB pilot still need validation on FILESERVER_IP.

See [manual pilot instructions](MANUAL-RECOVERY-PILOT.md). Browser upload approval is an administrator-only queue with manual download/placement; it neither intercepts direct SMB uploads nor adds domain-user SSO.

## Earlier isolated-workspace baseline

Validated on 2026-11-15 in an isolated Linux Docker test workspace. These are prototype checks with disposable and explicitly synthetic data.

- 48 Python tests passed with SQLite, and the same 48 passed against a separate disposable MySQL schema.
- 10 C# recovery-engine scenarios passed: stable baseline/modification/deletion, hash verification, restart/loop-limit persistence, corrupt objects, same-name conflicts, monitoring-only policy, unavailable root, oversized content, scope separation, exclusive state locking, and Linux link exclusion.
- React/TypeScript/Vite production build passed. Backend and runtime frontend Docker images built successfully. The full frontend Dockerfile uses the same verified Node build and Nginx runtime stages; a fresh full checkout build remains to be verified on the user's PC.
- 11 existing browser test groups passed: login, device management, folder registration, activity export, requests, service/database inspection, audit verification, connection recovery, dark theme, Arabic RTL, mobile layout, and absence of JavaScript errors.
- The new recovery page passed actual API reporting, search, desktop rendering, and 390px mobile checks without page overflow or JavaScript errors.
- The real C# worker preserved two versions and restored the latest disposable file with the expected SHA-256. The sample was observed restored within a 0.2-second polling interval; this is not a recovery-time guarantee.
- During an intentional ingestion-API outage, local recovery continued and three reports remained queued. They were acknowledged and drained after reconnection.
- PowerShell source syntax checks passed. Windows execution and Windows Service installation were not performed.

The five core container services were healthy during verification. The optional simulator supplied clearly labeled SIM-* monitoring records. Endpoint restrictions and directory writes remained disabled. No actual hospital device, AD/SMB connection, hospital file content, or production database was used.

To avoid a second large MySQL container on the limited test disk, validation reused the existing lab MySQL container with a separate FileGuard application schema, separate test schema, and independent application account. The repository's normal Compose file uses upstream mysql:8.4 and creates its own named volume. Environment-specific test overrides and all credentials remain outside the public source.

See ROADMAP.md for unimplemented production requirements. Windows NTFS behavior, Windows Service deployment, clinical consistency, high-volume tests, hardened repository access, signed updates, and full metadata restoration still require separate lab validation. No public web preview is deployed.

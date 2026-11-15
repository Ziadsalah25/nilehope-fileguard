# Validation record

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

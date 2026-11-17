# Reference DLP project review and recommended scope

This review inspected `FileGuard DLP Server.zip` as source and data only. No executable was run, no service was started, and no connection was made to `FILESERVER_IP`.

## What the reference project contains

| Area | Reference project behavior | Fit for NileHope FileGuard |
| --- | --- | --- |
| Console and alerts | Device inventory/heartbeats, upload and download logs, alerts, policy rules, risk views, and CSV export | Add DLP activity and policy status to the existing console and audit trail |
| Browser uploads | A Chrome/Edge extension observes file-picker, drag/drop, and clipboard uploads; domains can be allowed or gated for approval | Useful for managed Windows browsers; it does not cover every browser or every app on every device |
| USB | Extension/device allowlists and file-extension rules | Implement as a policy-based block with an explanation and audit event. Do not copy the reference's destructive file-wiping behavior |
| Desktop apps and clipboard | Watches selected messaging-app windows and clipboard file drops; can clear clipboard content | Add opt-in app policies, clear user notices, and an auditable block. Avoid silently terminating apps or destroying file contents |
| File Shield | Takes local vault copies, polls for changes, and restores after a delete | This is recovery after deletion, not pre-delete enforcement. The source skips its network-share wildcard during vault scanning, so it does not enforce deletion rules on the SMB server |
| Approvals | Admin approval flow, including Telegram integration | Keep approval and decision history in FileGuard. Treat external messaging integrations as optional because they can send file metadata or files outside the network |

## Security observations

- The ZIP includes an extension signing private-key file, a local database, and license state. Keep the archive private. If it has been shared outside trusted administrators, replace the extension signing key and prepare a clean distribution package.
- The standalone server code emits `Access-Control-Allow-Origin: *` and permits private-network browser requests. It also has a mix of admin-guarded and agent-facing routes. Before reusing its design, require a route-by-route authorization review, TLS, and an explicit browser-origin allowlist.
- The reference USB block path can wipe/delete a copied file. NileHope should block through a supported policy and retain the source file rather than destroying data as a response.
- Telegram file delivery and approval should be disabled until the hospital's data-handling rules explicitly allow it.

## Existing NileHope capabilities and gaps

The current project already has a React console, authenticated management APIs, device enrollment with individual agent keys, Windows/Linux monitoring, shared-folder registration, audit records, upload approvals, and a C# recovery worker that stores verified versions and can restore after deletion.

The main gaps are reliable server-side delete denial and complete per-user share activity collection. Browser upload enforcement, USB policy enforcement, and app/clipboard controls are also future modules. Recovery is not a substitute for delete prevention. The current selected priority is the one SMB file server at `FILESERVER_IP`; endpoint DLP can follow once the share pilot is proven.

## Recommended delivery order

1. **Protect the selected SMB share:** apply permissions on a new Windows Server pilot share. Ordinary staff can create/edit as required but receive neither `DELETE` on files nor `DELETE_CHILD` on parent folders. Check both NTFS and share-level effective access using the real UNC path. A server administrator or owner can still change permissions, so keep a logged break-glass administrator path.
2. **Monitor every intended share action:** improve the file-server collector beyond the current 5145 DELETE checks. Add scoped file-system event collection and correlation, record user/session/path/operation/result and client IP where available, and tune retention before broad success auditing.
3. **Host the console continuously on a VM:** use the existing Windows VM installer, stable internal DNS and trusted HTTPS, a persistent backed-up database, VM auto-start, and health/disk alerts. Use [the VM-only pilot guide](FILESERVER-VM-PILOT.md) for the current scope.
4. **Identify every share-client device:** enroll each supported Windows PC in monitor-only workstation mode (use the existing GPO deployment for domain-joined computers). Store a stable event-time relationship between SMB client IP, enrolled hostname, and the SMB account. Keep unique staff accounts; a shared login cannot identify which person used the PC. The previously reported HTTP 401 is an API authentication/enrollment rejection after a server response; it is separate from whether the CA certificate is trusted.
5. **Harden device trust and recovery:** keep per-device enrollment keys, rotate/revoke them, show actionable authentication errors, sign future installers/updates, and keep recovery copies in separately protected storage.
6. **Add endpoint DLP after the share pilot:** browser upload gating, USB device/file policies, and app/clipboard controls require agents or extensions on each PC that needs coverage. Start in monitor mode; show policy delivery/agent support before blocking. Never erase user files to enforce a rule, and do not upload file contents by default.
7. **Keep policy and audit in one place:** later add a DLP policy center for protected shares, gated web domains, USB rules, app/clipboard rules, and approvals, with alerts for agent drift and repeated denied operations.

For file shares, Windows ACLs are the authoritative control for SMB clients whether or not FileGuard is installed. A delete/rename check must include both a file's `DELETE` right and its parent directory's `DELETE_CHILD` right. Share-level and file-system permissions both affect remote effective access. A scoped SACL can record matching failed access attempts; broad auditing can create high event volume. Microsoft documents these behaviors in [DeleteFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-deletefile), [remote effective permissions](https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/access-checks-windows-apis-return-incorrect-results), and [Audit File System](https://learn.microsoft.com/windows/security/threat-protection/auditing/audit-file-system).

## Safe rollout sequence for `FILESERVER_IP`

1. Confirm the server hostname, Windows Server version, domain, exact share name, folder path, and the ordinary-user security group. An IP address alone is not enough to identify the share or its effective permissions.
2. Create a new, empty pilot folder/share and record its existing share and NTFS ACLs. Keep a tested backup and a privileged recovery account.
3. Configure and verify the pilot ACL for the ordinary-user group. Test file creation, editing, save-as, rename, delete, and the actual office/clinical applications using a normal user account.
4. Enable narrowly scoped failure auditing on that pilot folder. Check the resulting Security log and FileGuard attribution before expanding coverage.
5. Pilot the file-server agent and audit collection in monitoring mode; enable the NTFS denial only on the disposable share after the ordinary-user tests pass.
6. Expand by share with a recorded rollback for each change. Keep server administrators and backup/recovery identities separate from ordinary staff permissions. Add the endpoint modules later as a separately scoped deployment to user PCs.

Windows does not provide a reliable promise that even server administrators can never delete or re-permission data using ordinary NTFS ACLs. Owners control permissions, and delegated take-ownership privileges can bypass an ordinary-user denial. For stronger protection, combine staff deletion denial with a separately secured, versioned backup and recovery drills.

## Visual direction

The logo suggests this palette (approximate values):

- Blue `#3F80B3` for primary navigation, links, and protection controls.
- Pink `#D15F99` for brand accents and selected highlights; use a darker pink for small text.
- Leaf green `#8EAA50` for healthy/success status only.
- Navy `#243B53`, pale blue-gray `#F5F8FB`, and white for the main interface.

Use the blue/pink brand lightly, preserve high-contrast text, keep status colors distinct from brand colors, and retain the existing responsive layout and Arabic right-to-left mode.

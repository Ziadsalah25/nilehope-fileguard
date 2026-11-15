# Native Windows deployment templates

These scripts preserve the earlier monitoring deployment option. The current recommended console uses Docker; recovery has a separate C# lab worker.

Copy hospital-profile.example.json to hospital-profile.json and hospital-shares.example.csv to hospital-shares.csv locally, then fill in your approved server, domain, and share details. The populated files are ignored by Git. No actual hospital inventory is distributed.

Start-HospitalSetup.ps1 requires a prepared MySQL connection and trusted HTTPS, and validates the profile's machine/domain before installing. Start with -PreflightOnly. Review Windows rights, port ownership, and rollback before running installation on a server. The C# recovery service is not installed by these legacy monitoring scripts.

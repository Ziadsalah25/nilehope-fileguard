-- Execute locally in Workbench using a MySQL administrator account.
-- Creates a new application database without changing any existing database.
CREATE DATABASE IF NOT EXISTS nilehope_fileguard CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE nilehope_fileguard;
-- Then open deploy/windows/schema.mysql.sql in Workbench and execute it against this database.

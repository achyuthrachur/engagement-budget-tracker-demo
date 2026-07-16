# B2A Budget Tracker administrator runbook

## Production locations

- Application: `%LOCALAPPDATA%\Crowe\B2A Budget Tracker\App`
- Database: `%LOCALAPPDATA%\Crowe\B2A Budget Tracker\budget_tracker.db`
- Automatic backups: `%LOCALAPPDATA%\Crowe\B2A Budget Tracker\Backups`

The application retains the 20 most recent automatic backups.

## Installation and updates

1. Build with `build.bat`.
2. Code-sign `release\budget_tracker.exe` using the approved organizational certificate.
3. Distribute the contents of `release` through the approved internal channel.
4. The user runs `install.bat` without administrator rights.
5. For upgrades, save open work and run the newer installer. It stops the local tracker, replaces the executable and relaunches it. User data is outside the application directory and is preserved.

## Recovery

Use Settings to restore whenever possible. The restore endpoint runs SQLite integrity checks and verifies required tracker tables before replacement. It automatically preserves the current database.

For manual recovery:

1. Stop `budget_tracker.exe`.
2. Copy the current database to a safe location.
3. Copy a known-good backup over `budget_tracker.db`.
4. Relaunch and verify Settings reports the expected schema version.

## Support information

Collect:

- Windows version
- Application commit or release version
- Schema version shown in Settings
- Exact error message
- Whether the error occurred during preview or commit
- A copy of the database backup, only through an approved confidential-data channel

Never request Cognos time data through email or an unapproved file-transfer method.

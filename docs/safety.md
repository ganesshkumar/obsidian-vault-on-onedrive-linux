# Safety and verification

CAUTION: Bisync and full recovery can change local and cloud files.
Review generated files before use.
Keep independent, versioned backups.
Test with disposable data before relying on the setup.

The renderer writes local files only.
It does not install files, authenticate, start services, mount filesystems or initialize synchronization.

## Repository contents

The repository contains unit and helper templates, an account renderer, isolated fixture tests and documentation.
It excludes personal notes, OAuth configuration, raw journals, private source-path records and recovery archives.

Generated output contains the selected account and home path.
Git ignores this output.
Do not force-add it.
Keep real credentials out of the public clone.

## Tested behavior

The unittest suite runs rendered helpers against simulated service and process backends and isolated filesystem fixtures.
It checks:

- Rendering for account and home names that contain hyphens.
- Correct systemd mount-name escaping.
- Local filesystem guards other than the reference default.
- Refusal to overwrite existing output.
- Path validation.

Tests do not run sudo, real mounts or unmounts, notifications or authenticated cloud operations.
The reference installation's normal sync, bind identity, controlled mount cycle and connected boot were observed.
The exported package has not been deployed on every accepted filesystem or on a new machine.

The fixture suite does not establish these live results:

- Recovery after an interrupted real sync and finite lock expiry.
- Recovery after an unexpected rclone mount-process crash, including all dependency interactions.
- Cold boot without a connection through the convenience path.
- A scheduled, visible warning and recovery notification during a sustained outage.
- Agreement between all local and cloud files.
- Successful restoration from an independent backup.

## Privileges and permissions

The system rclone process runs as the configured normal user.
Root performs bind operations.
The watchdog requests the system mount unit.
User sync and health jobs run as the normal user.
System management does not move these programs into kernel space.

The mount uses `--allow-other`, which permits access beyond the mounting user.
On shared machines, review `/etc/fuse.conf` and filesystem permissions.
The inherited settings do not establish a minimum-access policy.
Test narrower permissions separately with root's bind operations.
Keep the installed helper owned by root.
Prevent other users from writing to it.

Use standard configuration and cache paths with the unchanged setup.
Custom XDG or rclone environment settings can select different accounts or saved state for the components.
An encrypted rclone configuration requires a separate design to supply secrets without user input.
Do not put a password in a unit file.
Keep passwords, tokens and sudo credentials out of the repository.

## Recovery and data changes

`restart-onedrive` makes private backups of the local vault and saved sync state.
It handles only a validated stale lock.
It recreates the mounts and waits for a new completed sync before resuming timers.
The normal conflict and deletion policies still apply in both directions.

The local backup does not preserve every version held only in the cloud.
Restoring saved state files does not reverse cloud operations.
Investigate malformed locks, live locks and locks with an uncertain owner.
The PID check can refuse a stale lock if another process has reused its recorded PID.

If full recovery fails, timers can remain paused.
Read the reported stage and logs before taking action.
Do not respond to an unfamiliar failure with repeated restarts, forced unmounts, application termination, listing deletion or `--resync`.

## Supported configuration

The setup supports:

- One normal local Linux account.
- One remote named `onedrive`.
- One selected root named `Obsidian`.
- Standard configuration, cache and state paths.
- An accessible local filesystem for the local folder.

The renderer accepts simple account and group names.
Home paths must exclude whitespace, traversal components and shell/systemd metacharacters.
The renderer rejects unsupported inputs instead of inserting arbitrary text into privileged configuration.

## Security reports

Before opening an issue, remove credentials, private notes, account or drive IDs and unredacted logs.
Review the content before publication.
Automated pattern checks do not replace a security audit.

# Safety and verification boundaries

This project can modify local and cloud data when you choose to run bisync or full
recovery. Review all generated files, keep independent versioned backups and test
with disposable data before relying on it. The renderer only creates local files;
it never installs, authenticates, starts services, mounts or initializes sync.

## What this repository contains

Current service/helper logic exported as reader-specific templates, a renderer,
portable fixture tests and documentation. Personal notes, OAuth configuration,
raw journals, private source-path manifests and recovery archives are excluded.
Generated output contains your account/home and is ignored by Git. Do not force-add
it or place real credentials anywhere in a public clone.

## What is tested

The unittest suite runs the rendered helpers against fake service/process backends
and isolated filesystem fixtures. Rendering includes hyphenated home/account names,
correct systemd mount-name escaping, non-default local filesystem guards, refusal
of existing output and path validation. Tests do not run sudo, real mount/unmount,
real notifications or authenticated cloud operations.

The originating installation's normal synchronization, bind identity, controlled
mount cycle and connected boot were observed. The sanitized package is not claimed
to have been deployed on every supported filesystem or on a clean machine.

Not proven by the fixture suite:

- Real interrupted bisync recovery after finite lock expiry.
- An unexpected mounted rclone-process crash and every dependency interaction.
- Offline cold boot through the convenience path.
- A sustained real outage producing a scheduled visible warning and recovery popup.
- Complete local/cloud file agreement or a tested independent backup restore.

## Privileges and permissions

The system rclone process runs as the rendered normal user. Root performs bind
mount operations and the watchdog requests the system mount unit. User sync and
health jobs run as that normal user. A system-managed process is still userspace.

The inherited mount uses `--allow-other`; review `/etc/fuse.conf` and filesystem
permissions on shared machines. It is not a least-privilege guarantee. Restricting
it or changing mount permissions is separate work and must be tested with root's
bind operations. The root-owned installed helper must not be writable by others.

Use standard config/cache paths with this unmodified stack. Custom XDG or rclone
config/cache environment overrides can make the user sync, system mount and
recovery command address different accounts/state. Encrypted rclone configuration
needs a separately designed unattended-secret mechanism, not a password in a unit.
Never put a password, token or sudo credential into this repository.

## Recovery is not rollback of data

`restart-onedrive` makes private local-vault and sync-state backups, handles only a
specifically validated stale lock, rebuilds mounts and waits for a fresh completed
sync before resuming timers. It uses the normal bidirectional deletion/conflict
policy. Local backup does not preserve every remote-only version. Restoring saved
state files does not undo cloud operations. Malformed, live or ambiguous locks
should be investigated, not overridden. The conservative PID check can refuse a
stale lock if its PID has since been reused.

Full recovery can keep timers paused on failure. Read the exact stage and logs;
do not repeatedly restart, force unmount, kill applications, delete listings or
run `--resync` in response to an unfamiliar failure.

## Scope

One normal local Linux account, one `onedrive` remote, one selected `Obsidian` root,
standard config/cache/state paths and an accessible local backing filesystem.
Simple account/group names and home paths without whitespace/metacharacters are
supported by the renderer. It intentionally rejects unsupported inputs instead of
trying to escape arbitrary privileged configuration text.

Open security reports as issues without credentials, private notes, account/drive
IDs or unredacted logs. Review before publication; automated pattern checks are
not a formal security audit.

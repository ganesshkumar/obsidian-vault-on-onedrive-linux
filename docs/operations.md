# Operations, recovery and removal

Use commands individually, read their output and stop on an unexpected result.
System service queries are generally available without sudo. Local privileged
inspection uses sudo only when you explicitly run a helper that requests it.
Never run the entire controller as root.

## Daily read-only checks

```sh
systemctl is-active rclone-onedrive.service
systemctl is-active onedrive-offline-bind.timer
systemctl --user is-active rclone-onedrive-offline.timer
systemctl --user is-active onedrive-health-check.timer
/usr/local/bin/onedrive-offline-bind --check
onedrive-health-check --check
systemctl --user show rclone-onedrive-offline.service \
    -p ActiveState -p Result -p ExecMainStatus \
    -p ExecMainStartTimestamp -p ExecMainExitTimestamp
```

Expect active mount/timers, verified bind identity, an `OK` health verdict, and a
recent successful completed sync (or a currently running sync). A oneshot normally
becomes inactive/dead after success. An active timer is not proof its job succeeds.
`--check` does not create health state or send notifications.

Targeted journals:

```sh
journalctl -u rclone-onedrive.service --no-pager -n 50
journalctl -u onedrive-offline-bind.service --no-pager -n 50
journalctl --user -u rclone-onedrive-offline.service --no-pager -n 50
journalctl --user -u onedrive-health-check.service --no-pager -n 50
```

Logs can contain private paths/filenames. Redact before sharing and never commit
raw logs or credentials. Journal visibility may depend on local permissions.

## Understand where a missing file should travel

- An ordinary `~/OneDrive/...` file uses rclone VFS upload/write-back.
- A correctly bound `~/OneDrive/Obsidian/...` file is local data, uploaded by the
  separate bisync job. Check that job's completion and its journal.
- If the bind is absent, the visible folder can instead be the cloud subtree.
  Avoid editing through the convenience path until identity is verified; use
  `~/.local/share/onedrive-offline/Obsidian` directly for offline work.

The monitor does not authenticate to OneDrive or audit every file. A deliberate,
disposable bidirectional file test is a stronger outcome check, but it changes
cloud/local data and should be planned, not run as a read-only diagnostic.

## Planned mount-only cycle

Close file managers, editors, shells with their working directory in either path,
and applications using the mount. Run as your normal user:

```sh
onedrive-cycle
```

This performs locally authenticated holder inspection, pauses the bind watchdog,
stops/checks the child, and only then requests parent stop. It restarts/verifies
the mount layer and resumes the watchdog timer. Managed bisync is independent and
is not stopped by this mount-only cycle. It does not perform a fresh sync.

If the child is busy, stop and close holders instead of using lazy/forced unmount
or killing applications. A failed child unmount is not a general systemd veto on
parent shutdown; do not substitute a raw parent restart for this controller.

The standalone preflight is:

```sh
onedrive-preflight
```

It changes no services/mounts, but requests sudo authentication locally for process
inspection; that authentication may update sudo's credential timestamp/audit log.
It rejects incomplete inspection. It is not a zero-system-side-effect command.

## Emergency full recovery

Use full recovery only after inspecting the specific failure and closing holders.
Inspect prerequisites first:

```sh
restart-onedrive --check
```

This mode validates configuration and mounted topology without performing repairs.
It is not the full privileged holder inspection, a data audit or a successful-sync
proof. Full recovery changes state and runs the normal bidirectional data policy:

```sh
restart-onedrive
```

Run it as the normal account, not `sudo restart-onedrive`. Enter any requested sudo
password directly in your local terminal. The workflow:

1. Checks configuration, mounted topology and application references.
2. Pauses the sync/bind timers and stops managed sync safely.
3. Copies local notes and saved sync state to a private timestamped recovery archive.
4. Archives/removes only a specifically validated stale session lock.
5. Unmounts child before parent using ordinary unmounts, then rebuilds/verifies them.
6. Requires a fresh successful bisync, independently rechecks that completion and
   only then resumes timers.

No automatic full resync, forced unmount, conflict-policy relaxation or deletion
policy override is added. Failure can leave timers paused deliberately. Read the
reported stage, private backup location and journals before further action.

Private recovery data lives under:

```text
~/.local/share/onedrive-recovery/
```

Do not publish it. This recovery backup is not a complete backup of remote-only
versions. Restoring local listings does not undo uploaded changes or deletions.

An old non-expiring lock can survive a reboot. Renewable `--max-lock 5m` protects
new lock lifecycles; it does not rewrite existing locks or override an active owner.
A process-ID reuse can cause conservative refusal. Never delete an ambiguous lock
or use `--resync` just to silence an error.

## Existing installations and upgrades

This repository is not an automatic migration from older user-managed cloud mounts
or arbitrary earlier scripts. Inventory the active system/user units, mount table,
file holders, local/remote data, baseline state and timer status before planning a
migration. Keep exactly one cloud owner for the parent mountpoint. Preserve the
existing bisync pair and saved state unless a deliberate backed-up reconciliation
is needed. Do not repeat fresh-install baseline initialization for an upgrade.

For updates, render into a new ignored output directory, compare it with installed
files and privately back up each destination before editing it. Decide exactly
which units must be paused; install only reviewed changes, reload the corresponding
manager and verify bind identity plus a new completed sync. There is no blanket
installer or automatic rollback. Reverting configuration cannot undo data changes.

## Optional removal / configuration rollback

This is **not part of the normal success path**. Do not run it after successful
setup merely because it appears in documentation.

First make independent backups and inventory what was installed. The commands below
assume a fresh installation using these exact standard destinations, with no
subsequent local replacement. For an upgrade, restore your own saved configuration
instead of blindly removing files. Keep a record of whether linger and
`user_allow_other` predated this setup.

1. Stop/disable the user timers. Let any in-flight bisync finish naturally before
   proceeding. Do not kill the job, remove its lock or delete its state.

```sh
systemctl --user disable --now rclone-onedrive-offline.timer
systemctl --user disable --now onedrive-health-check.timer
systemctl --user is-active rclone-onedrive-offline.service
```

   If sync is active/activating, wait and inspect its journal. A failed sync also
   needs investigation before concluding data is preserved. Once it has completed,
   stop an in-progress health check if necessary:

```sh
systemctl --user stop onedrive-health-check.service
```

2. Close holders and stop the watchdog. Remove/check the child **before** stopping
   the cloud service. Stop immediately on any failure; do not continue past a busy
   child. These are separate commands, not an unattended script.

```sh
sudo systemctl disable --now onedrive-offline-bind.timer
sudo systemctl stop onedrive-offline-bind.service
bind_unit=$(systemd-escape --path --suffix=mount "$HOME/OneDrive/Obsidian")
sudo systemctl stop "$bind_unit"
findmnt --mountpoint "$HOME/OneDrive/Obsidian"
```

   The last command must find no mount. Only then:

```sh
sudo systemctl disable --now rclone-onedrive.service
findmnt --mountpoint "$HOME/OneDrive"
```

   Require no remaining parent mount. Preserve any unexpected mount and investigate.

3. After reviewing file identities and retaining configuration backups, remove only
   the files installed by this project:

```sh
sudo rm -- /etc/systemd/system/rclone-onedrive.service \
    /etc/systemd/system/onedrive-offline-bind.service \
    /etc/systemd/system/onedrive-offline-bind.timer \
    "/etc/systemd/system/$bind_unit" \
    /usr/local/bin/onedrive-offline-bind

rm -- "$HOME/.config/systemd/user/rclone-onedrive-offline.service" \
    "$HOME/.config/systemd/user/rclone-onedrive-offline.timer" \
    "$HOME/.config/systemd/user/onedrive-health-check.service" \
    "$HOME/.config/systemd/user/onedrive-health-check.timer" \
    "$HOME/.local/bin/restart-onedrive" \
    "$HOME/.local/bin/onedrive-health-check" \
    "$HOME/.local/bin/onedrive-preflight" \
    "$HOME/.local/bin/onedrive-cycle"

sudo systemctl daemon-reload
systemctl --user daemon-reload
```

4. Keep the local notes, remote files, VFS cache, bisync listings, health state,
   credentials and private recovery archives. No data-directory deletion is part
   of these instructions. Verify the backing directory still contains your notes.
   Restore a previous cloud setup only after confirming no conflicting mount.

5. Revert linger or `/etc/fuse.conf` only if you enabled that setting solely for
   this setup and no other service relies on it. Use your private configuration
   backup; do not overwrite unrelated later edits. There is no need to uninstall
   shared packages merely to remove these units.

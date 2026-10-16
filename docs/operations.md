# Operations, recovery and removal

Run commands individually.
Read each result before continuing.
If a result is unexpected, stop.
Investigate before continuing.
Most system service queries work without sudo.
Some helpers request sudo authentication for privileged local inspection.
Run the controller as your normal user.

## Daily checks without state changes

Inspect services, timers, bind identity and the last sync result:

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

Check for these results:

- The cloud mount and timers are active.
- The helper verifies the bind identity.
- The health verdict is `OK`.
- The sync completed successfully recently or is currently running.

A successful oneshot service normally becomes inactive or dead after completion.
Check its result and timestamps as well as the timer state.
`--check` creates no health state and sends no notifications.

For details, read the relevant journal:

```sh
journalctl -u rclone-onedrive.service --no-pager -n 50
journalctl -u onedrive-offline-bind.service --no-pager -n 50
journalctl --user -u rclone-onedrive-offline.service --no-pager -n 50
journalctl --user -u onedrive-health-check.service --no-pager -n 50
```

CAUTION: Logs can contain private paths and filenames.
Remove private details before sharing them.
Keep raw logs and credentials out of Git.
Journal access depends on local permissions.

## Find the transfer path for a missing file

- An ordinary file under `~/OneDrive/...` uses the rclone VFS upload process.
- A file under a verified `~/OneDrive/Obsidian/...` bind changes the local folder.
  Bisync uploads it separately.
  Check the sync job's result and journal.
- If the bind is absent, the convenience path can show the cloud folder instead.
  Verify bind identity before editing through that path.
  For offline work, open `~/.local/share/onedrive-offline/Obsidian` directly.

The monitor does not authenticate to OneDrive or compare every file.
To check transfers in both directions, plan a separate test with disposable files.
That test changes local and cloud data.
Keep it separate from diagnostics that only inspect local state.

## Planned mount maintenance

Close file managers, editors and other applications that use either data path.
Close shells whose working directory is inside either path.
Then run the cycle command as your normal user:

```sh
onedrive-cycle
```

The controller requests sudo authentication for inspection of processes that use the mounts.
It pauses the bind watchdog, removes the child bind and checks that removal.
It then stops and restarts the parent mount.
After verifying the bind, it resumes the watchdog timer.
The independent bisync job continues under its own service.
This mount cycle performs no new sync.

If the child mount is busy, stop.
Close the processes that use it before continuing.
Do not use lazy or forced unmounts or kill applications to bypass the check.
A failed child unmount can still be followed by an ordinary systemd parent stop.
Use the controller's checked sequence rather than a direct parent restart.

To run the separate preflight check, use:

```sh
onedrive-preflight
```

Preflight leaves services and mounts unchanged.
It requests local sudo authentication to inspect processes.
Authentication can update sudo's credential timestamp and audit log.
If inspection is incomplete, preflight refuses to continue.

## Emergency recovery

Before recovery, inspect the specific failure.
Close processes that use the mounts.
Check the prerequisites:

```sh
restart-onedrive --check
```

This mode validates configuration and mount layout without repairs.
It does not perform the full privileged process inspection or compare file contents.
It also does not establish that a sync completed.

CAUTION: Full recovery changes state and runs the normal sync policy in both directions.
It can propagate deletions and conflicts.

To start full recovery, run:

```sh
restart-onedrive
```

Run the command as your normal user.
Do not use `sudo restart-onedrive`.
Enter a requested sudo password directly in your local terminal.

The command performs this sequence:

1. It checks configuration, mount layout and processes that use the mounts.
2. It pauses the sync and bind timers.
   It safely stops the managed sync.
3. It copies local notes and saved sync state to a private recovery archive with a timestamp.
4. It archives and removes only a validated stale session lock.
5. It unmounts the child before the parent with ordinary unmount operations.
   It then recreates and verifies both mounts.
6. It waits for a new successful sync.
   It independently checks that completion before resuming the timers.

The command keeps the normal conflict and deletion policies.
It does not add a full resync, forced unmount or deletion override.
If recovery fails, it can leave timers paused.
Read the reported stage, private backup location and journals before taking further action.

Private recovery data uses this directory:

```text
~/.local/share/onedrive-recovery/
```

Keep recovery data private.
The archive contains local data and sync state.
It does not preserve every version held only in the cloud.
Restoring saved listings does not undo cloud uploads or deletions.

An old lock without an expiry can survive a reboot.
`--max-lock 5m` gives new locks a renewable expiry.
It leaves existing lock data unchanged and does not override an active owner.
If another process reuses the recorded PID, the conservative check can refuse recovery.
Investigate ambiguous locks.
Do not delete them or use `--resync` to bypass an error.

## Existing installations and updates

Plan a migration before replacing an older cloud service or earlier scripts.
Record the following state:

- Active system and user units.
- The mount table.
- Processes that use the mounts.
- Local and remote data.
- Saved baseline state.
- Timer status.

Keep one cloud service responsible for the parent mountpoint.
Preserve the existing bisync pair and saved state.
If reconciliation is necessary, back up the data before planning that change.
Do not repeat fresh-install baseline setup for an update.

For an update, use these steps:

1. Render into a new ignored output directory.
2. Compare the output with the installed files.
3. Make a private backup of each destination before changing it.
4. Decide which units must be paused.
5. Install only reviewed changes.
6. Reload the applicable manager.
7. Verify bind identity and a new completed sync.

The project has no automatic migration or rollback installer.
Restoring old configuration cannot undo data changes.

## Remove the setup or restore configuration

Use this procedure only when you intend to remove the setup or restore earlier configuration.
After a successful installation, leave it installed.

CAUTION: The removal commands assume a fresh installation at the standard destinations shown below.
They also assume that no later local replacement has changed those files.

Before removal, make independent backups.
Record which files and units this project installed.
For an upgraded installation, restore your saved configuration instead of removing files without checking their origin.
Record whether linger and `user_allow_other` were enabled before this setup.

### 1. Stop the user timers

Disable the sync and health timers.
Check whether a sync is still running:

```sh
systemctl --user disable --now rclone-onedrive-offline.timer
systemctl --user disable --now onedrive-health-check.timer
systemctl --user is-active rclone-onedrive-offline.service
```

If sync is active or activating, wait for it to finish.
Inspect its journal if necessary.
Do not kill the job, remove its lock or delete its state.
Investigate a failed sync before concluding that the data is preserved.

After sync completes, stop a running health check if necessary:

```sh
systemctl --user stop onedrive-health-check.service
```

### 2. Remove the child mount before the parent

Close processes that use the mounts.
Stop the watchdog.
Then stop the child mount.
Inspect the result:

```sh
sudo systemctl disable --now onedrive-offline-bind.timer
sudo systemctl stop onedrive-offline-bind.service
bind_unit=$(systemd-escape --path --suffix=mount "$HOME/OneDrive/Obsidian")
sudo systemctl stop "$bind_unit"
findmnt --mountpoint "$HOME/OneDrive/Obsidian"
```

`findmnt` must show no child mount.
If the child remains mounted or an earlier command fails, stop.
Investigate before continuing.
Do not continue past a busy child.
Run these commands individually, outside an unattended script.

After confirming child removal, stop the cloud service:

```sh
sudo systemctl disable --now rclone-onedrive.service
findmnt --mountpoint "$HOME/OneDrive"
```

Check that the parent mount is gone.
If an unexpected mount remains, leave it unchanged.
Investigate the mount before continuing.

### 3. Remove only this project's files

Verify each file's identity against the installation record.
Keep the configuration backups.
Then remove only the files installed by this project:

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

### 4. Keep the data and saved state

Keep local notes, remote files, the VFS cache, saved bisync listings, health state, credentials and private recovery archives.
This procedure removes no data directories.
Check that the local folder still contains your notes.
Before restoring an earlier cloud setup, confirm that no competing mount exists.

### 5. Restore optional settings only when appropriate

Restore linger or `/etc/fuse.conf` only if this setup was their sole reason and no other service requires them.
Use your private configuration backup.
Preserve unrelated changes made after that backup.
Leave shared packages installed if other software uses them.

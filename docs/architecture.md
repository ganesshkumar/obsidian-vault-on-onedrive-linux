# Architecture

The project uses separate components for cloud access, local synchronization and the visible folder path.

```text
OneDrive cloud
    +-- rclone mount onedrive: --> ~/OneDrive (on-demand, read/write)
    |
    +-- rclone bisync onedrive:Obsidian
                    ^
                    | changes and deletions in both directions
                    v
        ~/.local/share/onedrive-offline/Obsidian
                    |
                    +-- bind --> ~/OneDrive/Obsidian
```

The local folder is `~/.local/share/onedrive-offline/Obsidian`.
Bisync connects it directly to `onedrive:Obsidian`.
A bind mount makes the same local files available at `~/OneDrive/Obsidian`.
This path is the convenience path.

The bind hides the cloud folder below that path.
Writes through a verified bind change the local files.
Bisync uploads those changes later.
Writes elsewhere in the FUSE mount use rclone's VFS upload process.

## Eight operational units

| Manager | Unit | Role |
|---|---|---|
| System | `rclone-onedrive.service` | Keeps the cloud mount running as the configured normal user |
| System | Path-derived `*.mount` | Establishes the local bind with root privileges |
| System | `onedrive-offline-bind.service` | Checks bind identity and requests repair within time limits |
| System | `onedrive-offline-bind.timer` | Schedules bind checks |
| User | `rclone-onedrive-offline.service` | Runs one local/cloud sync and exits |
| User | `rclone-onedrive-offline.timer` | Schedules the next sync five minutes after the previous run finishes, subject to timer accuracy |
| User | `onedrive-health-check.service` | Inspects health and stores notification state |
| User | `onedrive-health-check.timer` | Schedules the next check two minutes after completion, with 15-second accuracy |

There are four services, three timers and one explicit mount unit.
Each timer schedules work without a separate daemon process.
Successful oneshot services normally become inactive or dead after completion.

System management does not require root execution.
The system-managed programs still run in user space.
Systemd also detects the parent FUSE mount at runtime.
That detected mount does not add another configured service or cloud client to this inventory.

## Mount startup and shutdown

The system cloud service uses `Type=notify`.
It waits for the home filesystem and requests the bind watchdog.
The watchdog starts after the cloud service reports readiness.
It then requests the child bind mount.
This order avoids requesting the child before the parent mount is ready.

The child uses these dependencies:

```ini
Requisite=rclone-onedrive.service
After=rclone-onedrive.service
PartOf=rclone-onedrive.service
```

`Requisite` permits child startup only if the cloud service has already started.
It leaves an intentionally stopped cloud service stopped.
`After` sets the startup order.
`PartOf` carries systemd parent stop and restart actions to the child.
The watchdog also checks the cloud service's state before requesting repair.

A failed child unmount can still be followed by an ordinary parent stop.
For planned maintenance, `onedrive-cycle` pauses the watchdog and removes the child.
It checks that removal before requesting the parent stop.
Unexpected crashes and concurrent lifecycle requests can interrupt this sequence.
The design does not make those operations atomic.

The child mount is not enabled independently.
`bind,_netdev,nofail` associates its startup with network mounts without making it a required filesystem target dependency.
The files in the local folder remain local.

## Bind identity and probe limits

The bind helper reads `/proc/self/mountinfo` and checks:

- The exact FUSE source.
- Stacked mounts and unexpected nested mounts.
- The configured local filesystem type.
- Matching device and inode values from `stat` for the local source and visible target.

For Btrfs, the helper permits the mountinfo device identifier to differ from the `stat` device identifier.
If the existing bind is correct, the helper returns promptly.
Directory probes and mount-unit requests have time limits.
The watchdog service also has a finite startup timeout.

Uninterruptible kernel I/O can exceed these limits.
These operational checks do not isolate the privileged helper from a malicious local account.

## Sync policy

The setup uses one pair: `onedrive:Obsidian` and the local Obsidian folder.
It has no general folder selector, filter file or automatic first resync.

- `--resilient --recover --max-lock 5m` permits retries and recovery with renewable locks.
- A running job renews its finite lock every four minutes, so longer syncs can continue.
- Existing locks retain their own expiry timestamps.
  A new option does not rewrite an old lock that has no expiry.
- `--conflict-resolve none` avoids selecting a winner automatically.
  The default conflict handling can retain different versions under numbered conflict names.
- For bisync, `--max-delete 25` limits the permitted deletion percentage to 25%.

A large directory rename can appear as many deletions and additions.
It can therefore trigger the deletion guard.
Keep `--resync` and `--force` out of the normal service.
Investigate unknown locks before changing them.

## Health monitoring

The health monitor confirms an issue after three consecutive observations.
For an unchanged confirmed issue, it sends reminders at most once per hour.
A newly confirmed combination of issues can produce an earlier notification.
It reports recovery after all current checks pass.

The monitor records successful sync completions that it observes.
It does not reconstruct the complete sync history.
The stale-success threshold is 30 minutes of awake time, measured with a monotonic clock.
A new boot resets the observation window.
A long sync can produce a stale-success warning.
The monitor leaves the job running.

`--check` leaves counters unchanged and sends no notifications.
For normal monitoring, the service exit status reports whether inspection and state updates completed.
Read the logged `OK` or `ISSUES` verdict for the health result.
The monitor does not check whether its own timer is disabled.
It cannot report faults while stopped.

The monitor does not authenticate to the remote.
An active cloud process and readable local bind do not establish agreement for every cloud file.
Do Not Disturb or an absent notification daemon can prevent visible delivery after successful notification submission.

## Offline access and cache behavior

Use the local folder for dependable offline access.
After a cold boot without a connection, `~/OneDrive/Obsidian` can be unavailable until the bind is established.
It can also expose the underlying cloud folder temporarily.
Before using that path, verify the bind with `--check`.
Alternatively, open the local folder directly.
Test disconnected startup separately from a connected reboot.

The VFS cache contains files fetched on demand.
Open files and the interval between cache checks can cause usage to exceed its `20G` target.
Keep independent, versioned backups because synchronization can propagate file damage and deletions.

The original monotonic bind and sync timers retain `Persistent=true`.
Systemd applies its catch-up behavior only to `OnCalendar` timers.
It has no catch-up effect here.
The user unit's `network-online.target` belongs to the user manager, separately from the system manager's target.
Network startup order does not ensure continued cloud access.

## References

- https://rclone.org/bisync/
- https://rclone.org/commands/rclone_mount/
- https://rclone.org/onedrive/
- https://raw.githubusercontent.com/rclone/rclone/v1.75.1/cmd/bisync/lockfile.go
- https://raw.githubusercontent.com/rclone/rclone/v1.75.1/cmd/bisync/deltas.go
- https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html
- https://www.freedesktop.org/software/systemd/man/latest/systemd.mount.html
- https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html
- https://wiki.archlinux.org/title/Systemd/User
- https://systemd.io/NETWORK_ONLINE/
- https://help.obsidian.md/backup

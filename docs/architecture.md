# Architecture

This project separates **access**, **synchronization**, and **presentation**.

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

The bind hides the underlying cloud view at that path. It is not another copy.
Writes through a verified bind modify the local backing tree; bisync uploads them
later. Ordinary writes elsewhere in the FUSE mount use rclone's VFS write-back.

## Eight operational units

| Manager | Unit | Role |
|---|---|---|
| System | `rclone-onedrive.service` | Continuous cloud mount; process runs as the configured normal user |
| System | Path-derived `*.mount` | Privileged local bind |
| System | `onedrive-offline-bind.service` | Bounded validation/repair request |
| System | `onedrive-offline-bind.timer` | Periodic bind checking |
| User | `rclone-onedrive-offline.service` | Oneshot direct local/cloud sync |
| User | `rclone-onedrive-offline.timer` | Five minutes after the previous run finishes, subject to timer accuracy |
| User | `onedrive-health-check.service` | Inspection and notification bookkeeping |
| User | `onedrive-health-check.timer` | Two minutes after the previous check finishes, with 15-second accuracy |

There are four services, three timers and one explicit mount unit. Timers do not
have one daemon process each. Successful oneshots normally become inactive/dead.
System-managed does not mean kernel-space execution or necessarily root execution.
Systemd also observes the parent FUSE mount dynamically; this is not another cloud
client or another configured service in the count above.

## Lifecycle

The system cloud service uses `Type=notify`, waits for its home filesystem, and
requests the bind watchdog. The watchdog is ordered after cloud readiness. Only
then does it request the child mount, avoiding premature activation of the
runtime-observed parent mount dependency.

The child uses:

```ini
Requisite=rclone-onedrive.service
After=rclone-onedrive.service
PartOf=rclone-onedrive.service
```

`Requisite` refuses a child start without an already-started cloud service; it does
not start an intentionally stopped cloud service. `After` supplies ordering, and
`PartOf` propagates systemd parent stop/restart actions. The watchdog checks the
cloud's state as well. Unlike a startup requirement, this choice does not turn a
repair attempt into an indirect request to start the cloud service.

**Ordering is not a veto:** a failed child unmount does not guarantee an ordinary
parent stop will be cancelled. For planned maintenance, `onedrive-cycle` pauses
the watchdog and successfully removes/checks the child before requesting parent
stop. Unexpected crashes and arbitrary concurrent lifecycle requests are not an
atomic transaction guaranteed by this design.

The mount is not enabled independently. `bind,_netdev,nofail` associates its
convenience-path lifecycle with network mounting without making it a mandatory
filesystem-target boot requirement. The actual backing directory remains local.

## Identity and bounded probes

The bind helper reads `/proc/self/mountinfo`, validates the exact FUSE source,
refuses stacked/unexpected nested mounts, checks the configured backing filesystem
and compares source/target stat device/inode pairs. It deliberately does not equate
Btrfs's mountinfo device identifier with stat's device identifier.

Existing correct binds return promptly. Directory probes and mount-unit requests
are bounded, and the watchdog service has a finite startup timeout. This limits
ordinary stalls, not uninterruptible kernel I/O. The helper is operationally
conservative, not a sandbox against a malicious local account.

## Sync policy

- `--resilient --recover --max-lock 5m` permits retry/recovery with renewable locks.
  The finite lock is renewed every four minutes; five minutes is not a run limit.
- Existing locks contain their own expiry timestamp. Adding this option does not
  rewrite an old non-expiring lock; do not delete unknown locks blindly.
- `--conflict-resolve none` avoids automatically selecting a winner; differing
  conflicts can be preserved under numbered conflict names.
- **Bisync's `--max-delete 25` is a 25% deletion guard, not a 25-file cap.**
- There is one pair: `onedrive:Obsidian` and the local Obsidian tree. There is no
  general folder-selection UI, filter file, or automatic initial resync.

Large directory renames can appear as many deletions/additions and trigger guards.
The normal service must never contain `--resync` or `--force`.

## Monitoring

The health monitor confirms the same issue on three consecutive observations,
reminds at most hourly for an unchanged confirmed issue, and reports recovery when
all current checks pass. A new confirmed combination can alert earlier. It tracks
observed successful sync completions, not a complete historical audit. A long
running sync can trigger a stale-success warning; the monitor does not kill it.

The stale threshold is 30 minutes of monotonic/awake time. New boots reset the
observation window. `--check` neither updates counters nor sends notifications.
The service exit status only says that inspection/bookkeeping ran; use its logged
`OK` or `ISSUES` verdict. It does not check its own timer being disabled, and cannot
warn about anything while it is stopped.

No authenticated remote probe is performed. An active cloud process and readable
local bind do not prove arbitrary cloud paths or full content agreement. Desktop
submission success does not guarantee visibility during Do Not Disturb or without
a running notification daemon.

## Offline and cache caveats

Use the backing path for dependable local offline access. After a disconnected
cold boot, `~/OneDrive/Obsidian` can be unavailable or temporarily expose the cloud
view until the bind is established. Gate application use on `--check` or open the
backing path directly. A connected reboot does not prove offline cold boot.

The VFS cache is not a complete offline copy. Its `20G` target is not an absolute
hard ceiling; open files and polling can cause it to be exceeded. Sync is not a
backup; use an independent versioned data-backup system.

The original monotonic bind/sync timers retain `Persistent=true` for fidelity.
Systemd only gives that setting catch-up effect with `OnCalendar`, so it has no
such effect here. User-unit `network-online.target` also does not refer to the
system manager's network target; network ordering is not a cloud-connectivity SLA.

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

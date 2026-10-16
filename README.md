# OneDrive Offline Sync

On-demand OneDrive access, a genuinely local Obsidian working tree, a bind-mounted
convenience path, and systemd supervision with desktop health notifications.

```text
onedrive:          -- rclone mount --> ~/OneDrive
onedrive:Obsidian  <---- bisync ----> ~/.local/share/onedrive-offline/Obsidian
                                               |
                                               +-- bind --> ~/OneDrive/Obsidian
```

This is a reviewed set of templates and helper scripts for an advanced Linux
setup, **not a one-click cloud client**. There is one selected folder root,
`Obsidian`. Ordinary mounted files and offline notes use different upload paths.
**Sync propagates deletions and is not a backup.** Read [Safety](docs/safety.md)
and [Architecture](docs/architecture.md) before installation.

## What is included

- Eight unit definitions: four system-managed and four user-managed.
- An identity-checking bind watchdog with bounded probes.
- A user health monitor with confirmation, reminder suppression and recovery notices.
- A conservative emergency `restart-onedrive` command.
- A narrower planned `onedrive-cycle` controller and read-only preflight.
- A preview-first renderer and isolated regression tests.

Templates contain no fixed personal account or home path. The renderer derives
those from your account or accepts explicit, validated values. It uses
`systemd-escape` for the mount filename, including hyphens in account/home names.
Generated files in `build/` are private local output and must not be committed.

## Requirements and supported scope

- Linux with systemd and a normal local user account with sudo for mount setup.
- Python 3.10+, rclone with bisync, FUSE3, Bash, util-linux (`findmnt`, `mount`,
  `umount`, `systemd-escape` via systemd), and `notify-send` for desktop alerts.
- A local home/backing filesystem available when the system cloud service starts.
  Per-login encrypted/network homes need additional integration not supplied here.
- A configured remote named **`onedrive`**, using the standard
  `~/.config/rclone/rclone.conf` and `~/.cache/rclone` paths.
- A remote directory **`onedrive:Obsidian`** with real files, plus independent
  backups of important local/remote data before initial reconciliation.
- A desktop notification daemon for visible alerts. Systemd linger alone does not
  create a desktop session or make popups visible.

The reference installation used rclone 1.75.1 and systemd 262. Other versions and
filesystems need their own deployment checks; fixture success is not a clean-install
certification. The renderer accepts local Btrfs, ext2/3/4, XFS, F2FS and ZFS type
guards. It rejects network/FUSE backing types and home paths containing whitespace,
traversal, or shell/systemd metacharacters. The remote and selected root are fixed
in this version; adding another root requires a separately reviewed sync pair.

### Arch Linux packages

If needed, review and perform a full upgrade/install, not a partial upgrade:

```sh
sudo pacman -Syu rclone fuse3 python libnotify util-linux
```

Do not run package commands merely because you cloned this repository. Other
distributions must provide equivalent tools. No package operation is performed by
the renderer or tests.

## Setup: fresh installation only

Follow each stage separately and stop on an error. Do not paste the whole README
as an unattended shell script. Run ordinary commands as your normal user; use sudo
only where explicitly shown. No password belongs in a file or chat.

For an existing installation, see [Operations and removal](docs/operations.md).
Do not create competing cloud mounts or reinitialize an established bisync pair.

### 1. Clone and inspect

Clone this repository from its GitHub page, then enter the clone:

```sh
cd onedrive-offline-sync
python3 -B -m unittest discover -s tests -v
```

Read `templates/`, `tools/configure.py` and the safety documentation. Tests use
rendered templates with fake backends and temporary fixtures; they never perform
real cloud sync, sudo, mounts or notifications.

### 2. Configure your own OneDrive account securely

```sh
rclone config
```

Create a remote named `onedrive` using the official
[OneDrive backend instructions](https://rclone.org/onedrive/). Do not publish the
resulting configuration. Ensure it is readable/writable only by your user:

```sh
chmod 600 "$HOME/.config/rclone/rclone.conf"
```

The unchanged templates require standard config/cache locations. Remove or review
custom `RCLONE_CONFIG`, `RCLONE_CACHE_DIR`, XDG or systemd environment overrides
before using this setup. An encrypted rclone config needs a separate unattended
secret-loading design, not a password embedded in the service.

Confirm `onedrive:Obsidian` is the intended existing cloud directory. Authenticated
rclone commands can refresh/write credentials locally; they are not strictly
read-only diagnostics even when they only list cloud files.

### 3. Check for conflicting configuration and prepare directories

Check for existing owners before installing anything:

```sh
findmnt --mountpoint "$HOME/OneDrive"
systemctl --user list-unit-files 'rclone-onedrive*' 'onedrive-health-check*'
systemctl list-unit-files 'rclone-onedrive*' 'onedrive-offline-bind*'
```

No mount/no matching units is expected on a fresh installation. If a mount,
matching unit, helper or selected-folder data already exists, stop and inventory
it. Back up configuration outside this public clone and design a migration rather
than overwriting it. In particular, **never enable a user cloud service alongside
the system cloud service with the same mountpoint**.

Create an empty mountpoint and the local backing directory:

```sh
mkdir -p "$HOME/OneDrive" "$HOME/.local/share/onedrive-offline/Obsidian"
```

Check the mountpoint is empty; files placed underneath a mount are hidden, not
uploaded automatically by the act of mounting. Keep the local backing directory
outside the mounted tree.

The inherited FUSE options include `--allow-other`. Read your distribution's
`/etc/fuse.conf` guidance and enable `user_allow_other` only after reviewing the
access implications and backing up that configuration. This option broadens
access beyond the mounting user. Do not assume the inherited permissions are
appropriate on a shared workstation. Narrower options require separate testing
with root's bind operations.

### 4. Initialize the sync baseline deliberately

**This stage changes data and local synchronization state. Do not run it on an
already initialized pair. Pause competing clients/edits, independently back up both
sides and read the [bisync manual](https://rclone.org/bisync/) first.**

For the specific fresh-install case where the cloud is authoritative and the
local directory is empty, first preview downloading the cloud data:

```sh
offline="$HOME/.local/share/onedrive-offline/Obsidian"
rclone copy onedrive:Obsidian "$offline" --dry-run
```

After reviewing the plan, download it:

```sh
rclone copy onedrive:Obsidian "$offline"
```

This is not appropriate if you already have local-only edits. Reconcile those
manually with backups instead. Both roots must contain the intended data before
automation is activated; empty listings have special bisync safeguards.

Preview a first baseline with an explicit **cloud-preferred** resync policy:

```sh
rclone bisync "$offline" onedrive:Obsidian \
    --resync --resync-mode path2 --dry-run \
    --conflict-resolve none --max-delete 25 \
    --resilient --recover --max-lock 5m
```

Only after reviewing that preview and accepting its consequences, run the same
first-baseline operation without `--dry-run`:

```sh
rclone bisync "$offline" onedrive:Obsidian \
    --resync --resync-mode path2 \
    --conflict-resolve none --max-delete 25 \
    --resilient --recover --max-lock 5m
```

`path2` prefers cloud versions during this first reconciliation. This is a
**first-baseline procedure**, not the normal recurring command. Dry runs can still
write local state/logs and refresh authentication. Never add `--resync` or `--force`
to the recurring service. Bisync's `--max-delete 25` means **25%**, not 25 files.

Saved listings normally live in `~/.cache/rclone/bisync`. Preserve them. The full
recovery command deliberately refuses to invent a missing baseline.

### 5. Render files for your account

Preview first; this does not write generated files:

```sh
python3 -B tools/configure.py
```

Check the detected account, group, home path, filesystem type and mount-unit name.
Then generate a new `build/` tree:

```sh
python3 -B tools/configure.py --write
```

The renderer never installs, starts units, authenticates, or runs synchronization.
It refuses an existing output directory. To keep multiple reviewed renderings,
use a new ignored output path, for example `--output rendered/review-2`.

Explicit parameters are available for review/testing:

```sh
python3 -B tools/configure.py \
    --user reader --group reader --home /home/reader --local-fs-type ext4
```

Do not install files rendered for a different account. Inspect all generated
files, including `build/settings.json`. Keep the clone/rendering on a trusted,
user-controlled local filesystem. Do not commit generated output.

### 6. Install reviewed files without overwriting an existing stack

These commands are for a fresh installation. **Before copying, verify that every
corresponding destination below is absent, including symlinks.** If any exists,
stop, back it up privately and use a deliberate migration. The commands below are
manual installation commands, not an overwrite-protected installer.

```sh
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"

sudo install -o root -g root -m 0755 \
    build/bin/onedrive-offline-bind /usr/local/bin/onedrive-offline-bind

sudo install -o root -g root -m 0644 build/system/* /etc/systemd/system/

install -m 0644 build/user/* "$HOME/.config/systemd/user/"

install -m 0755 \
    build/bin/restart-onedrive \
    build/bin/onedrive-health-check \
    build/bin/onedrive-preflight \
    build/bin/onedrive-cycle \
    "$HOME/.local/bin/"
```

Ensure `~/.local/bin` is on your PATH. No sudoers modification or passwordless sudo
rule is required. The recovery/controller commands request authentication locally
when needed.

Validate the installed units before starting them:

```sh
systemd-analyze verify /etc/systemd/system/rclone-onedrive.service \
    /etc/systemd/system/onedrive-offline-bind.service

systemd-analyze --user verify \
    "$HOME/.config/systemd/user/rclone-onedrive-offline.service" \
    "$HOME/.config/systemd/user/rclone-onedrive-offline.timer" \
    "$HOME/.config/systemd/user/onedrive-health-check.service" \
    "$HOME/.config/systemd/user/onedrive-health-check.timer"

sudo systemctl daemon-reload
systemctl --user daemon-reload
```

The explicit child mount has a path-derived filename in `build/system/`; inspect
and validate that unit too. It is activated only after the parent FUSE mount is
available. It is not independently enabled at boot.

### 7. Start and verify the mount layer

```sh
sudo systemctl enable --now rclone-onedrive.service
sudo systemctl start onedrive-offline-bind.service
/usr/local/bin/onedrive-offline-bind --check
```

Expected bind message:

```text
Verified existing local Obsidian bind.
```

Check that the cloud process runs as your account and the bind is mounted:

```sh
systemctl show rclone-onedrive.service -p User -p ActiveState -p Result
bind_unit=$(systemd-escape --path --suffix=mount "$HOME/OneDrive/Obsidian")
systemctl status "$bind_unit" --no-pager
findmnt -R "$HOME/OneDrive" -o TARGET,SOURCE,FSTYPE
```

Only after these checks succeed:

```sh
sudo systemctl enable --now onedrive-offline-bind.timer
```

If the helper refuses an unexpected mount, do not force/lazy-unmount it or weaken
the guard just to make the check pass. Investigate the actual topology.

### 8. Verify a real sync before enabling its timer

The baseline from stage 4 must already exist. Run one normal service invocation:

```sh
systemctl --user start rclone-onedrive-offline.service
systemctl --user show rclone-onedrive-offline.service \
    -p ActiveState -p Result -p ExecMainStatus \
    -p ExecMainStartTimestamp -p ExecMainExitTimestamp
```

Require a fresh completed run: `inactive`, `Result=success`, exit status 0 and
current start/exit timestamps. Inactive/dead is expected after a successful oneshot.
The oneshot has no arbitrary short startup deadline; wait rather than interrupting
a large sync just because a mount startup was quick.

Then enable periodic sync:

```sh
systemctl --user enable --now rclone-onedrive-offline.timer
```

Confirm a disposable note can traverse both directions under your own approved
test procedure. Service success is not an independent audit of every cloud file.

### 9. Enable desktop monitoring

```sh
onedrive-health-check --check
onedrive-health-check --test-notification
systemctl --user start onedrive-health-check.service
systemctl --user enable --now onedrive-health-check.timer
journalctl --user -u onedrive-health-check.service --no-pager -n 25
```

Expect `OneDrive health: OK` and a visible test popup if your desktop allows it.
The notification test sends one popup but does not change monitor state.
`--check` is read-only and does not increment alert counters. The scheduled monitor
writes private bookkeeping at `~/.local/state/onedrive-health/state.json`.

`Result=success` for the monitor means the inspection ran; read its **OK/ISSUES**
verdict. A real sustained-failure warning/recovery cycle is a separate live test,
not something to fake by repeatedly invoking `--check`.

### 10. Optional boot behavior and planned restart check

If you want user sync/monitor jobs to run before login and after logout, review
and enable lingering explicitly:

```sh
sudo loginctl enable-linger "$USER"
```

This keeps user services alive without an interactive session; it does not make
notifications visible while no desktop is running. Without linger, user jobs
normally depend on the user manager being started by login.

For a planned mount-only cycle, close applications/terminals using either data
path, then run as your normal user:

```sh
onedrive-cycle
```

It pauses the bind watchdog, removes/checks the child before requesting parent
stop, restarts the mount layer, verifies the bind and resumes its timer. It does
not run bisync. On failure, read the stage/error; a timer may remain paused.

No reboot is needed to activate these files. At a later chosen reboot, recheck the
cloud service, bind identity, timers and a fresh successful sync from that boot.
A connected boot does not establish offline cold-boot behavior.

## Normal use and emergencies

Read [Operations and removal](docs/operations.md) for commands, diagnostics,
maintenance, data-preservation caveats and uninstallation.

Use the local backing path directly when dependable offline access is required.
`~/OneDrive/Obsidian` depends on the parent cloud mount becoming available first.
The VFS cache is not a complete offline copy, and the 20G cache target is not an
absolute hard limit.

`restart-onedrive --check` only validates prerequisites. Full `restart-onedrive`
is an emergency, data-changing recovery workflow: it makes private local backups,
may archive a validated stale lock, rebuilds mounts and runs the normal bidirectional
policy. It is not needed on a routine schedule. It cannot promise a complete
remote-data rollback or recover every ambiguous failure automatically.

## Development and verification

```sh
python3 -B -m unittest discover -s tests -v
```

Tests require systemd tools for path escaping but do not require a running systemd
manager. Temporary fixtures do not touch your installed units or data. See
[Safety](docs/safety.md) for exactly what is and is not proven. The export preserves
the installed logic except for
reader-specific rendering, portable test loaders, and an additional read-only mount
topology gate before recovery can pause jobs or handle a stale lock. The existing
immediate pre-unmount topology recheck is retained. This packaging safety fix does
not modify the originating installation. Do not describe a successful render as a
tested clean installation on another machine.

For a reviewed local clone, see [Publishing](docs/publishing.md) before creating a
public GitHub repository. Account-specific builds and private recovery data must
remain excluded; the owning GitHub account is necessarily visible in its URL.

## Repository layout

```text
templates/system/   root-manager unit templates
templates/user/     user-manager unit templates
templates/bin/      watchdog, monitor, recovery, preflight and cycle templates
tools/configure.py  preview/write renderer only
tests/              rendering and helper regression fixtures
docs/               architecture, safety and operations
```

MIT licensed; see [LICENSE](LICENSE). Review the code and protect your data.

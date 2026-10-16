# Obsidian Vault on OneDrive for Linux

Keep an Obsidian vault available offline on Linux with systemd.
Use OneDrive to synchronize the vault and access other cloud files on demand.
This project supplies systemd units, helper scripts and desktop health notifications.

The setup was tested on Arch Linux.
Before using another distribution, check dependencies, executable paths and permissions.
Other distributions have not been tested.

```text
onedrive:          -- rclone mount --> ~/OneDrive
onedrive:Obsidian  <---- bisync ----> ~/.local/share/onedrive-offline/Obsidian
                                               |
                                               +-- bind --> ~/OneDrive/Obsidian
```

The setup uses one selected folder, `Obsidian`.
Ordinary cloud files use the rclone mount.
The local Obsidian folder uses a separate bisync job.
Installation requires manual checks and configuration.

CAUTION: Synchronization can copy deletions to other devices.
Keep independent backups.
Read [Safety](docs/safety.md) and [Architecture](docs/architecture.md) before installation.

## Included files

- Eight unit definitions: four for the system manager and four for the user manager.
- A bind watchdog that checks directory identity and limits probe duration.
- A health monitor that confirms faults, limits repeated alerts and reports recovery.
- The `restart-onedrive` command for emergency recovery.
- The `onedrive-cycle` command for planned mount maintenance.
- A preflight helper for checks before maintenance.
- A renderer that previews account settings before it writes files.
- Regression tests that use isolated fixtures.

The templates contain no fixed personal account or home path.
The renderer detects account settings or accepts validated values.
It uses `systemd-escape` to create the mount filename, including paths with hyphens.
Generated files in `build/` contain private account settings.
Do not commit them.

## Requirements and supported scope

- Linux with systemd and a normal local user account.
- Sudo access for mount setup.
- Python 3.10 or later, rclone with bisync, FUSE3, Bash and util-linux.
- `findmnt`, `mount` and `umount` from util-linux, plus `systemd-escape` from systemd.
- `notify-send` and a desktop notification daemon for visible alerts.
- A local home filesystem that is available when the system cloud service starts.
- A remote named `onedrive` with an existing `onedrive:Obsidian` directory that contains files.
- The standard configuration path, `~/.config/rclone/rclone.conf`, and cache path, `~/.cache/rclone`.
- Independent backups of important local and remote files before initial reconciliation.

Encrypted homes that open at login and network homes require additional integration.
This project does not supply that integration.
Linger keeps user services available without login.
Visible notifications still require a desktop session.

The reference installation used rclone 1.75.1 and systemd 262.
Check other versions and filesystems before deployment.
Fixture tests do not establish that a fresh installation will work on another machine.

The renderer accepts local Btrfs, ext2/3/4, XFS, F2FS and ZFS filesystem guards.
It rejects network and FUSE filesystems for the local folder.
It also rejects home paths with whitespace, traversal components or shell/systemd metacharacters.
This version fixes the remote name and selected folder.
An additional folder requires a separate sync pair and review.

### Arch Linux packages

If packages are missing, review the following full upgrade and installation command.
Do not use a partial upgrade.

```sh
sudo pacman -Syu rclone fuse3 python libnotify util-linux
```

Run package commands only when the installation requires them.
On other distributions, install equivalent tools.
The renderer and tests do not install packages.

## Fresh installation

Complete one stage at a time.
If a command fails, stop.
Investigate the error before continuing.
Run commands as your normal user unless the command explicitly includes sudo.
Enter passwords only in your local terminal.
Do not store passwords in files or send them in chat.

For an existing installation, use [Operations and removal](docs/operations.md).
Keep one cloud mount owner.
Preserve the existing bisync pair and its saved state.

### 1. Clone and inspect

Clone this repository from its GitHub page.
Enter the clone.
Run the test suite:

```sh
cd obsidian-vault-on-onedrive-linux
python3 -B -m unittest discover -s tests -v
```

Read `templates/`, `tools/configure.py` and the safety documentation.
The tests use rendered templates, simulated service backends and temporary fixtures.
They do not run real cloud sync, sudo, mounts or notifications.

### 2. Configure your OneDrive account

Start rclone configuration:

```sh
rclone config
```

Create a remote named `onedrive`.
Follow the official [OneDrive backend instructions](https://rclone.org/onedrive/).
Keep the resulting configuration private.
Restrict file access to your user:

```sh
chmod 600 "$HOME/.config/rclone/rclone.conf"
```

The templates use standard configuration and cache paths.
Before setup, check custom `RCLONE_CONFIG`, `RCLONE_CACHE_DIR`, XDG and systemd environment settings.
Remove or adjust settings that select different paths.
An encrypted rclone configuration requires a separate method to supply secrets without user input.
Do not put the password in a service file.

Confirm that `onedrive:Obsidian` is the intended cloud directory.
Authenticated rclone commands can refresh credentials and write the local configuration.
This can occur even when a command only lists cloud files.

### 3. Check existing configuration and prepare directories

Check for existing mount owners and units:

```sh
findmnt --mountpoint "$HOME/OneDrive"
systemctl --user list-unit-files 'rclone-onedrive*' 'onedrive-health-check*'
systemctl list-unit-files 'rclone-onedrive*' 'onedrive-offline-bind*'
```

A fresh installation should have no matching mount or units.
If matching units, helpers, mounts or selected-folder data exist, stop.
Record what exists before you plan a migration.
Back up the configuration outside this public clone.
Do not overwrite an existing setup.

CAUTION: Two cloud services can compete for the same mountpoint.
Do not enable a user cloud service alongside the system cloud service.

Create the mountpoint and local folder:

```sh
mkdir -p "$HOME/OneDrive" "$HOME/.local/share/onedrive-offline/Obsidian"
```

Check that the mountpoint is empty.
A mount hides existing files beneath it.
Mounting does not upload those hidden files.
Keep the local folder outside the cloud mount.

The FUSE options include `--allow-other`, which permits access beyond the mounting user.
Before changing `/etc/fuse.conf`, read your distribution's guidance.
Make a backup of the file.
Enable `user_allow_other` only after you review the access policy.
On a shared workstation, check who can read the mounted files.
Test narrower permissions separately with root's bind operations.

### 4. Initialize the sync baseline

CAUTION: This stage changes data and saved sync state.
Use it only for a fresh pair.
Do not repeat it for an initialized pair.

Pause other sync clients.
Stop edits on both sides.
Make independent backups of both sides.
Read the [bisync manual](https://rclone.org/bisync/) before continuing.

The following procedure assumes that the cloud has the correct files and the local folder is empty.
If local files contain unsynchronized edits, reconcile them manually with backups first.

Preview the download:

```sh
offline="$HOME/.local/share/onedrive-offline/Obsidian"
rclone copy onedrive:Obsidian "$offline" --dry-run
```

Check the proposed changes.
If they are correct, download the cloud files:

```sh
rclone copy onedrive:Obsidian "$offline"
```

Before enabling automation, check that both folders contain the intended files.
Bisync applies special safeguards to empty listings.

Preview the first baseline with a policy that prefers cloud versions:

```sh
rclone bisync "$offline" onedrive:Obsidian \
    --resync --resync-mode path2 --dry-run \
    --conflict-resolve none --max-delete 25 \
    --resilient --recover --max-lock 5m
```

Review the preview and the conflict choices.
If you accept the changes, run the first baseline without `--dry-run`:

```sh
rclone bisync "$offline" onedrive:Obsidian \
    --resync --resync-mode path2 \
    --conflict-resolve none --max-delete 25 \
    --resilient --recover --max-lock 5m
```

For this first reconciliation, `path2` prefers cloud versions.
Dry runs can still write local state and logs or refresh authentication.
Keep `--resync` and `--force` out of the recurring service.
For bisync, `--max-delete 25` means 25% of files.

Saved listings normally use `~/.cache/rclone/bisync`.
Preserve these listings.
The recovery command refuses to create a missing baseline.

### 5. Generate files for your account

Preview the account settings without writing generated files:

```sh
python3 -B tools/configure.py
```

Check the account, group, home path, filesystem type and mount-unit name.
Then generate a new `build/` directory:

```sh
python3 -B tools/configure.py --write
```

The renderer writes files only.
It does not install files, start units, authenticate or synchronize data.
If the output directory exists, it refuses to continue.
For another reviewed set of files, use a new ignored path such as `--output rendered/review-2`.

To review explicit account settings, use:

```sh
python3 -B tools/configure.py \
    --user reader --group reader --home /home/reader --local-fs-type ext4
```

Install only files generated for the intended account.
Inspect all generated files, including `build/settings.json`.
Keep the clone and generated files on a trusted local filesystem under your control.
Do not commit generated output.

### 6. Install the reviewed files

CAUTION: These copy commands can overwrite destination files.
They do not check for existing files or symbolic links.

Before copying, check that every corresponding destination is absent, including symbolic links.
If any destination exists, stop.
Back it up privately and plan a migration.
Use these commands only for a fresh installation:

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

Check that `~/.local/bin` is on your PATH.
Leave the sudoers configuration unchanged.
The recovery and cycle commands request sudo authentication locally when necessary.

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

The child mount has a path-derived filename in `build/system/`.
Inspect that unit.
Validate it before startup.
The setup activates it after the parent FUSE mount becomes available.
Do not enable the child mount independently at boot.

### 7. Start and check the mounts

Start the cloud service and request the bind check:

```sh
sudo systemctl enable --now rclone-onedrive.service
sudo systemctl start onedrive-offline-bind.service
/usr/local/bin/onedrive-offline-bind --check
```

The expected bind message is:

```text
Verified existing local Obsidian bind.
```

Check that the cloud process uses your account.
Check the bind and mount layout:

```sh
systemctl show rclone-onedrive.service -p User -p ActiveState -p Result
bind_unit=$(systemd-escape --path --suffix=mount "$HOME/OneDrive/Obsidian")
systemctl status "$bind_unit" --no-pager
findmnt -R "$HOME/OneDrive" -o TARGET,SOURCE,FSTYPE
```

If these checks pass, enable the bind timer:

```sh
sudo systemctl enable --now onedrive-offline-bind.timer
```

If the helper rejects an unexpected mount, investigate the mount layout.
Do not force or lazily unmount it to pass the check.
Keep the validation checks in place.

### 8. Check a completed sync before enabling its timer

Confirm that the baseline from stage 4 exists.
Start one normal sync and inspect its result:

```sh
systemctl --user start rclone-onedrive-offline.service
systemctl --user show rclone-onedrive-offline.service \
    -p ActiveState -p Result -p ExecMainStatus \
    -p ExecMainStartTimestamp -p ExecMainExitTimestamp
```

Check for a newly completed run with these values:

- `ActiveState=inactive`.
- `Result=success`.
- Exit status 0.
- Start and exit timestamps from this invocation.

A successful oneshot service normally becomes inactive or dead after it exits.
The sync service has no short startup deadline.
Allow a large sync to finish.
Do not interrupt it because it takes longer than mount startup.

After the sync succeeds, enable its timer:

```sh
systemctl --user enable --now rclone-onedrive-offline.timer
```

Plan a test with disposable notes to check transfers in both directions.
A successful service result does not establish agreement for every cloud file.

### 9. Enable desktop monitoring

Run the health check.
Send a test notification.
Then start the monitor:

```sh
onedrive-health-check --check
onedrive-health-check --test-notification
systemctl --user start onedrive-health-check.service
systemctl --user enable --now onedrive-health-check.timer
journalctl --user -u onedrive-health-check.service --no-pager -n 25
```

Check for `OneDrive health: OK` and a visible test notification.
The test sends one notification without changing monitor state.
Desktop settings can prevent the notification from appearing.

`--check` does not update state, increment alert counters or send notifications.
The scheduled monitor stores private records at `~/.local/state/onedrive-health/state.json`.

Read the monitor's `OK` or `ISSUES` verdict in the log.
Its `Result=success` value means that inspection completed.
A sustained failure, scheduled warning and recovery notification require a separate live test.
Repeated `--check` calls do not test that sequence.

### 10. Choose boot behavior and check a planned restart

To run user jobs before login and after logout, review the effects of linger.
If required, enable it:

```sh
sudo loginctl enable-linger "$USER"
```

Linger keeps the user manager running without an interactive session.
Notifications still require a desktop session.
Without linger, login normally starts the user manager and its jobs.

For planned mount maintenance, close applications and terminals that use either data path.
Then run the cycle command as your normal user:

```sh
onedrive-cycle
```

The command pauses the watchdog, removes the child bind and checks that it is gone.
It then restarts the parent mount, verifies the bind and resumes the timer.
It does not run bisync.
If it fails, read the reported stage and error.
A timer can remain paused.

These files take effect without a reboot.
After a later reboot, check the cloud service, bind identity, timers and a new successful sync.
A connected boot tests startup with network access only.

## Normal use and emergencies

Use the local folder directly when you need dependable offline access.
`~/OneDrive/Obsidian` depends on the parent cloud mount becoming available first.
The VFS cache contains files fetched on demand.
It can exceed the `20G` size target between checks and while files remain open.

`restart-onedrive --check` validates prerequisites only.
Full `restart-onedrive` changes data and sync state.
It creates private local backups, handles a validated stale lock, rebuilds mounts and runs the normal sync policy.
Use it for emergencies rather than on a recurring schedule.
It cannot undo all remote changes or resolve every ambiguous failure.

See [Operations and removal](docs/operations.md) for diagnostics, maintenance, recovery and removal.

## Development and verification

Run the fixture suite:

```sh
python3 -B -m unittest discover -s tests -v
```

Tests require systemd tools for path escaping.
They do not require a running systemd manager.
The temporary fixtures leave installed units and personal data unchanged.
[Safety](docs/safety.md) lists the tested behavior and remaining live tests.

The export retains the installed logic with these changes:

- Templates supply settings for the selected account.
- Test loaders work independently of the source machine.
- Recovery checks the mount layout before it pauses jobs or handles a stale lock.

Recovery also retains the layout check immediately before unmounting.
These export changes leave the source installation unchanged.
A successful render checks file generation only.
Test a fresh installation separately on another machine.

Before creating a public GitHub repository, read [Publishing](docs/publishing.md).
Exclude generated builds and private recovery data.
The GitHub account name remains visible in the repository URL.

## Repository layout

```text
templates/system/   root-manager unit templates
templates/user/     user-manager unit templates
templates/bin/      watchdog, monitor, recovery, preflight and cycle templates
tools/configure.py  preview/write renderer only
tests/              rendering and helper regression fixtures
docs/               architecture, safety and operations
```

The project uses the MIT license.
See [LICENSE](LICENSE).

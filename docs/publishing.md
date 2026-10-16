# Publish the repository

Publication is a separate action from file generation and installation.
The renderer and tests do not create a GitHub repository, push code or change visibility.
Complete the following review before publication.

## Review before the first public push

1. Run the local tests.
   Inspect the tracked files and history:

   ```sh
   python3 -B -m unittest discover -s tests -v
   git diff --check
   git ls-files
   git status --short
   git log --format=fuller --all
   ```

2. Review filenames, file contents and commit identity.
   Exclude personal notes, real account and home paths, raw journals, OAuth configuration, tokens, recovery archives and generated builds.
   Inspect all history as well as the current files.
   Gitignore does not remove secrets already tracked by Git.
   If a secret appears in a commit, stop publication.
   Rotate the exposed secret.
   Removing the current file or adding an ignore rule leaves the earlier exposure unresolved.

3. Check the local contributor identity in the prepared commit.
   This repository uses a neutral identity and leaves the global Git identity unchanged.
   Public GitHub URLs and metadata still identify the owner account.

4. Check that generated output remains untracked:

   ```sh
   git check-ignore build/settings.json
   git ls-files build rendered private backups
   ```

   The second command must print nothing.
   If no settings file has been generated, its absence is expected.
   Check any other output paths that you used.

5. Require a clean working tree and a reviewed commit before publication.
   Make a deliberate decision to publish publicly.
   Do not use an unreviewed `git add -A` immediately before a push.
   Automated scans can miss private content.

## Create and push a public repository

CAUTION: The creation command below makes the repository contents public immediately.
Run it only after completing the review and deciding to publish.

From the repository root, authenticate locally with the supported GitHub CLI workflow.
Keep tokens out of chat, source files and remote URLs.
Inspect authentication and existing remotes:

```sh
gh auth status
git remote -v
```

Confirm that the name is unused and no conflicting origin exists.
Then run:

```sh
gh repo create obsidian-vault-on-onedrive-linux \
    --source . --remote origin --public --push \
    --description 'Obsidian vault sync on Linux with OneDrive, rclone, bind mounts and systemd monitoring; tested on Arch Linux'
```

If the name exists or the remote conflicts, stop.
Inspect the existing repository or remote.
Choose another unused name if necessary.
Do not force-push over another project or change an unrelated repository's visibility.

## Verify the published repository

Read the remote repository settings and commit ID:

```sh
gh repo view --json nameWithOwner,url,visibility,defaultBranchRef
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Require `PUBLIC` visibility and default branch `main`.
Check that the local and remote commit SHAs match.
Then inspect the published file tree:

```sh
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api "repos/$repo/git/trees/main?recursive=1" --jq '.tree[] | select(.type == "blob") | .path'
```

Compare this file list with `git ls-files`.
Check that the remote contains no generated output or private files.

This package has no CI workflow.
Report local tests as local tests.
A successful upload does not establish that CI passed.
Test a new-machine installation and real failure recovery separately.

## Respond to accidental publication

A visibility change or repository deletion cannot recall existing clones, caches or forks.
If credentials were exposed, rotate them immediately.
Review data exposure and history cleanup separately.

Obtain a separate decision before deleting a repository, replacing remote history or changing visibility.
These actions do not automatically reverse publication.

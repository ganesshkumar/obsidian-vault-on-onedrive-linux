# Publishing this local repository

Publication is separate from rendering or installing. Nothing in the renderer or
tests creates a GitHub repository, pushes code or changes visibility. Do not publish
until the review and privacy gates below are complete.

## Before the first public push

1. Run the full local suite and inspect all tracked files:

   ```sh
   python3 -B -m unittest discover -s tests -v
   git diff --check
   git ls-files
   git status --short
   git log --format=fuller --all
   ```

2. Review filenames, content and commit identity. Exclude personal notes, real
   account/home paths, raw journals, OAuth config, tokens, recovery archives and
   generated builds. Inspect all history, not just the current checkout. Gitignore
   does not remove previously tracked secrets. If a secret has ever been committed,
   stop and rotate it; a new ignore rule or deleting the current file is inadequate.

3. This repository uses a neutral local contributor identity for the prepared
   commit. It does not change global Git identity. GitHub ownership/account names
   remain visible in public URLs and metadata; sanitizing code cannot hide them.

4. Confirm ignored output remains untracked:

   ```sh
   git check-ignore build/settings.json
   git ls-files build rendered private backups
   ```

   The second command must print nothing. Absence of one generated settings file
   is fine if you have not rendered; inspect your actual output paths as well.

5. Require a clean working tree, a reviewed commit and a deliberate decision to
   publish publicly. Do not use an unreviewed `git add -A` immediately before push.
   No automated scan is a formal guarantee that a repository is safe to publish.

## Create a new public GitHub repository and push

Run this only after deciding to publish, from the repository root. Authenticate
locally with the supported GitHub CLI workflow; never put a token into chat, source
files or a remote URL. First inspect authentication and existing remotes:

```sh
gh auth status
git remote -v
```

If the name is unused and no conflicting origin exists:

```sh
gh repo create onedrive-offline-sync \
    --source . --remote origin --public --push \
    --description 'On-demand OneDrive mount, selected-folder bisync, bind integration and systemd health monitoring'
```

This command makes the contents public immediately. If the name exists or the
remote conflicts, stop and inspect it; do not force-push over another project or
change an unrelated repository's visibility. Choose an unused name deliberately.

## Read back publication

```sh
gh repo view --json nameWithOwner,url,visibility,defaultBranchRef
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Require PUBLIC visibility, default branch `main`, and matching local/remote commit
SHAs. Then inspect the published tree, not just a successful push message:

```sh
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api "repos/$repo/git/trees/main?recursive=1" --jq '.tree[] | select(.type == "blob") | .path'
```

Compare this inventory with `git ls-files`; ensure no generated output or private
files appeared. There is no CI workflow included in this package: do not claim CI
passed based on local tests, rendering or successful upload. A clean-machine install
and real failure/recovery integration tests remain separate acceptance checks.

## If publication must be reversed

Do not assume making a repository private or deleting it recalls existing clones,
caches or forks. Rotate any exposed credentials immediately, and handle data/history
remediation explicitly. Destructive repository deletion, force-pushing history or
visibility changes are separate decisions, not an automatic rollback action.

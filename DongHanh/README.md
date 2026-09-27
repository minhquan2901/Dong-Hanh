# DongHanh account storage

Account credentials are stored by the server, not in browser JavaScript or `localStorage`:

- Students: `accounts2.json`
- Parents: `accounts3.json`
- Older records in `accounts.json` remain readable for compatibility.

Locally, the files are under `TaiKhoan/` by default. To keep accounts on Render across deploys, first back up account files from the current service, create a Persistent Disk, mount it at `/var/data`, and set this environment variable for the service:

```text
DONGHANH_DATA_DIR=/var/data/donghanh-accounts
```

Copy any existing `accounts.json`, `accounts2.json`, and `accounts3.json` backup into `/var/data/donghanh-accounts/` before starting the new deployment. If a legacy file is still available in `TaiKhoan/` and its persistent destination does not exist yet, the app migrates it once. Files in `TaiKhoan/` are intentionally ignored by Git, so local account files are not uploaded during deployment. Without a mounted persistent disk, files written by the server may be lost when Render replaces the instance; if the old filesystem has already been reset before backup, the app cannot recover those accounts.

The dashboard's logout only removes the browser's signed-in profile; it does not remove server-side account files. Refreshing the page also does not delete accounts.

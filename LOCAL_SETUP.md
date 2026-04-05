# Local Setup Notes

Verified on this machine in `/Users/rc/Project/codex-manager`.

## Install

```bash
uv sync --python 3.11
```

## Run

```bash
uv run python webui.py --host 127.0.0.1 --port 15555 --access-password testpass
```

## Notes

- The project requires Python 3.10 or newer.
- A local SQLite database is created under `data/database.db` on first start.
- Logs are written under `logs/`.

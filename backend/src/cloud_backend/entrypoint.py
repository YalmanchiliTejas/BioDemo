"""Load secret files without interpolating credentials into Compose or Terraform."""
import os
import sys
from pathlib import Path


def main():
    os.environ["DATABASE_URL"] = Path(os.environ["DATABASE_URL_FILE"]).read_text().strip()
    if sys.argv[1] == "api":
        import uvicorn
        uvicorn.run("src.cloud_backend.api:create_app", factory=True, host="0.0.0.0", port=8000,
                    proxy_headers=False, access_log=False, log_level="warning")
    elif sys.argv[1] == "dispatcher":
        from .dispatcher import main as run
        run()
    else:
        raise ValueError("Unknown service")


if __name__ == "__main__":
    main()

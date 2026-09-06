"""Start the local monitoring dashboard."""

import uvicorn

from monitor.main import dashboard_bind


if __name__ == "__main__":
    host, port = dashboard_bind()
    uvicorn.run("monitor.main:app", host=host, port=port, reload=False)

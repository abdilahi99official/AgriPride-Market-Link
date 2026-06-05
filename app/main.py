from fastapi import FastAPI

app = FastAPI(
    title="AgriPride Kibaigwa MarketLink",
    description="Human-supervised maize price transparency platform for Kibaigwa.",
    version="0.1.0",
)


@app.get("/")
def read_root() -> dict[str, str]:
    """Return the service status for the first local build."""
    return {
        "service": "AgriPride Kibaigwa MarketLink",
        "status": "running",
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    """Provide a lightweight deployment health check."""
    return {"status": "healthy"}
"""Start the Web UI server."""
import uvicorn

if __name__ == "__main__":
    port = 8000
    print(f"\n  🀄 http://localhost:{port}\n")
    uvicorn.run(
        "backend.server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )

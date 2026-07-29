## Python Backend

This `server` folder is now a FastAPI backend.

Run it locally with:

```powershell
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

Deployment note:

- `runtime.txt` pins Render to Python 3.11 so packages like `pydantic-core` install from prebuilt wheels instead of attempting a Rust source build on Python 3.14.

Frontend note:

- Set `VITE_API_URI` to `http://localhost:5000`
- The React client will then call the Python backend

What remains here:

- `app/` FastAPI application code
- `main.py` backend entrypoint
- `requirements.txt` Python dependencies
- `rss-fetcher/` Rust RSS helper used by the Python backend

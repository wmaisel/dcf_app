# DCF App (Alpha Vantage backend on Render)

React/Vite frontend plus FastAPI backend. All deployments use Alpha Vantage for fundamentals.

## Prerequisites
- Python 3.10+
- Node.js 18+ (with npm)

## Backend (FastAPI)
Local (requires Alpha Vantage API key):
```bash
python3 -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate
pip install -r requirements.txt
# set your Alpha Vantage key in the environment before running
export ALPHAVANTAGE_API_KEY=your_key_here
uvicorn backend.main:app --reload --port 8000
```
Hosted on Render:
- Set environment variables:
  - `ALPHAVANTAGE_API_KEY` (required)
  - `ALLOWED_ORIGINS` (comma-separated; include your frontend origin)
  - `FUNDAMENTALS_CACHE_TTL` (optional, seconds; default 900)
- Start command: `uvicorn backend.main:app --host 0.0.0.0 --port 10000`
- Port: 10000 (Render default for FastAPI)

## Frontend (Vite/React)
```bash
npm install
# Set the backend URL (Render)
echo "VITE_API_BASE=https://<your-render-backend-url>" > .env.local
npm run dev
```
For local backend, use `VITE_API_BASE=http://localhost:8000` or rely on the default.

## End-to-end check
1) Backend running (local or Render).  
2) Frontend running (`npm run dev`) with `VITE_API_BASE` pointed correctly.  
3) In the app, enter `AAPL`, click “Load Fundamentals”, then “Run Valuation”. You should see fundamentals/DCF outputs and no CORS or 401 errors in the browser console.

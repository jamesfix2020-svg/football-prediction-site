# Hosting BetWise Predictor

This project has a Python backend, so host it as a web service, not as a static-only site.

## Recommended: Render

1. Create a GitHub repository.
2. Upload these files from `football-predictor-website`:
   - `index.html`
   - `server.py`
   - `requirements.txt`
   - `Procfile`
   - `render.yaml`
   - `README.md`
3. Go to Render and create a new Web Service.
4. Connect your GitHub repository.
5. Use these settings:
   - Runtime: Python
   - Build command: `python3 -m py_compile server.py`
   - Start command: `python3 server.py`
6. Deploy.
7. Open your Render URL and test:
   - `/`
   - `/api/health`
   - `/api/fixtures?date=2026-09-27&days=7&league=all`

## Railway

1. Create a new Railway project from GitHub.
2. Select this repository.
3. Set start command to:

```bash
python3 server.py
```

4. Deploy and open the public domain Railway gives you.

## VPS

```bash
sudo apt update
sudo apt install -y python3
cd football-predictor-website
PORT=8080 python3 server.py
```

For production, put Nginx/Caddy in front and run the app with a process manager such as systemd.

## Important

GitHub Pages, basic Netlify static hosting, or plain file upload hosting will show the design but automatic match loading will fail because those options do not run `server.py`.

# Share Veriify With Friends Via ngrok

## One-Time Setup (5 minutes)

### 1. Install ngrok
```
brew install ngrok
```

### 2. Sign up for free account
Go to: https://ngrok.com
Sign up → Dashboard → Copy your auth token

### 3. Add your token
```
ngrok config add-authtoken YOUR_TOKEN_HERE
```

## Every Time You Want To Share

### Run everything with one command:
```
cd ~/interview-coach
./start.sh
```

### You'll see a URL like:
```
https://abc123.ngrok-free.app
```

### Share that URL with friends!
They open it in Chrome → sign up → start interviewing.
No download. No installation. Works on any device.

> **First visit:** ngrok's free tier shows a one-time "You are about to visit…"
> interstitial. Friends just click **Visit Site** and they're in.

## Important Notes
- Keep your Mac ON (and awake) while friends are using it
- Max 3–4 friends at the same time (M4 handles it fine)
- The URL changes every time you restart ngrok
- Free tier: 1 tunnel, unlimited connections
- PostgreSQL (accounts/history) and Ollama (the AI) both run **locally** on your
  Mac — friends never need them; everything is proxied through the one URL.

## Stop Everything
```
cd ~/interview-coach
./stop.sh
```

## Troubleshooting
- **"Cannot connect to server"** on signup → the backend isn't up. Re-run
  `./start.sh` and watch for `✅ Database connected` and `Uvicorn running`.
- **"Database unavailable"** → Postgres isn't running:
  `brew services start postgresql@17` then `python3 setup_db.py`.
- **Interview won't start over the public URL** → already handled: the app now
  uses a secure `wss://` WebSocket on https pages, so real-time streaming works
  through ngrok. Make sure friends use the full `https://…ngrok-free.app` link.
- **ngrok: "authentication failed"** → you skipped step 3; add your authtoken.

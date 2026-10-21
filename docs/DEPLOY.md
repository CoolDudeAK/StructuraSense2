# Putting StructuraSense on GitHub and Vercel (beginner guide)

## The one thing to understand first
StructuraSense has two halves:

| Half | What it is | Where it can live |
|---|---|---|
| **Front end** (the pages you see) | plain HTML/JS/CSS in the `frontend/` folder | **Vercel** (free) |
| **Back end** (Python + database + live updates) | `backend/`, a Flask server with an SQLite database and a live-data stream | **Render / Railway / Fly.io** (needs a server that stays switched on) |

**Vercel cannot run the back end.** Its servers sleep between requests and cannot keep a database file or the live stream open. So the plan is:
GitHub (stores the code) -> Vercel (shows the pages) -> Render (runs the back end).
Your Arduino stays on your own laptop; use the "Connect Data" page's browser reader or the bridge script, pointed at your hosted back end.

## Part 1 - Put the code on GitHub
1. Make a free account at github.com and click **New repository**. Name it `structurasense`. Leave it **Private**. Do not tick "Add a README".
2. Install **GitHub Desktop** (desktop.github.com) and sign in.
3. In GitHub Desktop: *File > Add local repository* and choose the unzipped `structurasense` folder. If it says it is not a repository, click **create a repository**.
4. Type a summary such as `First version`, click **Commit to main**, then **Publish repository** (keep "Keep this code private" ticked).
5. You should now see your files on github.com. The `.gitignore` already keeps your database, uploads and passwords out.

## Part 2 - Host the back end (Render)
1. Make a free account at render.com using "Sign in with GitHub".
2. Click **New > Blueprint**, pick your `structurasense` repository. Render reads `render.yaml` for you.
3. It asks for two values:
   * `SS_DEMO_PASSWORD` - **choose your own password**; the one in the README is public.
   * `SS_CORS_ORIGIN` - leave blank for now, fill it in after Part 3.
4. Click **Apply**. After a few minutes you get an address like `https://structurasense-api.onrender.com`. Open `https://.../api/health` - you should see `"ok": true`.
5. Note: the free instance has no permanent disk, so data resets when it restarts. The blueprint asks for the cheapest paid instance (about US$7/month) so the database survives. For a one-day demo the free tier is fine (set the plan to `free` and delete the `disk:` block in `render.yaml`).

## Part 3 - Host the front end (Vercel)
1. Open `frontend/config.js` in the repository and change the line to your Render address:
   `window.SS_API_BASE = "https://structurasense-api.onrender.com";`
   Commit and publish again in GitHub Desktop.
2. Make a free account at vercel.com using "Continue with GitHub", click **Add New > Project**, import `structurasense`.
3. Leave *Framework Preset* as **Other**. Vercel reads `vercel.json` (publishes the `frontend` folder, no build step). Click **Deploy**.
4. You get an address like `https://structurasense.vercel.app`.
5. Go back to Render > your service > **Environment**, set `SS_CORS_ORIGIN` to exactly that Vercel address (no slash at the end) and save. Render restarts.
6. Open the Vercel address and sign in. If the page says it cannot reach the server, check `config.js` and `SS_CORS_ORIGIN` first.

## Part 4 - Connecting your hardware to the hosted back end
* **Arduino over USB:** keep using the browser reader / `tools/serial_bridge.py` on your laptop, but give it the Render address as the server.
* **ESP32 / scripts:** set the server address in the firmware to the Render address and use the device key from *Connect Data*.

## What to tell people
Hosting is for showing the prototype. Passwords are hashed and device keys exist, but this is prototype-grade security: do not put real client data in it. See "What is real?" inside the app.

## Cheaper all-in-one alternative
Skip Vercel entirely: deploy only the Render service. Flask already serves the pages at its own address, and no CORS setting is needed.

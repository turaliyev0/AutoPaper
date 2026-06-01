# API authentication — Google OAuth

AutoPaper uses **Google as the identity provider**. There is no username/password login on this API.

After Google verifies the user, the API returns a short-lived **session token** (`access_token`) used as `Authorization: Bearer …` on protected routes. That token is **not** a Google API key — it only proves “this browser completed Google sign-in.”

## Google Cloud setup

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → **Credentials**
2. **Create credentials** → OAuth client ID → **Web application**
3. **Authorized redirect URIs** (required):
   ```
   http://localhost:8000/api/auth/google/callback
   ```
   Add your production API URL the same way when you deploy.
4. Copy **Client ID** and **Client secret** into `.env`:
   ```env
   GOOGLE_CLIENT_ID=....apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=...
   AUTOPAPER_GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
   AUTOPAPER_FRONTEND_URL=http://localhost:5173
   AUTOPAPER_SESSION_SECRET=long-random-string
   ```

5. OAuth consent screen: add test users while in “Testing” mode.

## Sign-in flows

### A) Browser redirect (simplest)

1. Open `http://localhost:8000/api/auth/google/login`
2. Sign in with Google
3. Redirect to `{AUTOPAPER_FRONTEND_URL}/auth/callback?access_token=...`
4. Frontend stores `access_token` (e.g. `localStorage`) and sends:
   ```http
   Authorization: Bearer <access_token>
   ```

### B) SPA — Google Identity Services (recommended for React)

1. Load GIS with your `GOOGLE_CLIENT_ID` (same as backend).
2. On success, POST the `credential` (Google **id_token**) to:
   ```http
   POST /api/auth/google/verify
   Content-Type: application/json

   { "credential": "<google_id_token>" }
   ```
3. Response:
   ```json
   { "access_token": "...", "token_type": "bearer", "expires_in": 86400 }
   ```

`GET /api/auth/status` returns `google_client_id` and URLs for the frontend bootstrap.

## Protected routes

All `/api/*` except:

- `GET /api/health`
- `GET /api/auth/status`
- `GET /api/auth/google/login`
- `GET /api/auth/google/callback`

## SSE

```js
const token = localStorage.getItem("access_token");
const es = new EventSource(
  `${API}/api/runs/${runId}/stream?access_token=${encodeURIComponent(token)}`
);
```

## Local dev without Google

```env
AUTOPAPER_AUTH_DISABLED=1
```

No sign-in required; do not use in production.

## What we removed

`POST /api/auth/token` (username/password) is **not** used. Use Google only.

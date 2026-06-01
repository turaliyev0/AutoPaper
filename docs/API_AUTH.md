# API authentication (OAuth2 + JWT)

## Quick start (Swagger)

1. Start API: `python run_stable.py`
2. Open http://localhost:8000/docs
3. **POST `/api/auth/token`** — username `admin`, password from `.env` (`AUTOPAPER_AUTH_PASSWORD`, default `changeme`)
4. Click **Authorize** → paste token (or use OAuth2 flow in Swagger)
5. Call protected routes

## Token request

```http
POST /api/auth/token
Content-Type: application/x-www-form-urlencoded

username=admin&password=changeme
```

Response:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

Use header on all protected routes:

```http
Authorization: Bearer eyJ...
```

## SSE (live log stream)

`EventSource` cannot send `Authorization`. Pass the JWT as a query parameter:

```js
const token = "…";
const es = new EventSource(
  `${API_URL}/api/runs/${runId}/stream?access_token=${encodeURIComponent(token)}`
);
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AUTOPAPER_JWT_SECRET` | Yes (if auth on) | HMAC secret for JWT |
| `AUTOPAPER_AUTH_USER` | Recommended | Login username |
| `AUTOPAPER_AUTH_PASSWORD` | Recommended | Login password |
| `AUTOPAPER_JWT_EXPIRE_MINUTES` | No | Default `1440` (24h) |
| `AUTOPAPER_AUTH_DISABLED` | No | `1` = no auth (dev only) |
| `AUTOPAPER_AUTH_USERS` | No | `user:pass,user2:pass2` |

## Public endpoints

- `GET /api/health`
- `POST /api/auth/token`
- `GET /api/auth/status`

All other `/api/*` routes require a valid bearer token unless `AUTOPAPER_AUTH_DISABLED=1`.

## New artifact endpoints (auth required)

| Method | Path |
|--------|------|
| GET | `/api/runs/{id}/artifacts` |
| GET | `/api/runs/{id}/artifacts/{path}` |
| GET | `/api/runs/{id}/validation` |
| GET | `/api/runs/{id}/editor-plan` |
| GET | `/api/runs/{id}/sections` |
| GET | `/api/runs/{id}/standardized` |
| PATCH | `/api/runs/{id}/standardized` |

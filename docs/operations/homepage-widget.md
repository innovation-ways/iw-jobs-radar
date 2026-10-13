# Homepage widget

Shows on a [Homepage](https://gethomepage.dev) dashboard what waits in the inbox and whether Jobs Radar is up (ADR-065). Read-only, no personal data.

## 1. Let the dashboard reach the API

The API listens on `127.0.0.1` by default. Set the address in the untracked `.env` (`0.0.0.0` for every interface, or the LAN address of the host), then recreate the API:

```bash
JOBS_RADAR_API_BIND=0.0.0.0
./jobs-radar.sh --rebuild api
```

The API has no authentication in V1: every device that can reach the port can read it. Keep it off untrusted networks. Check from the dashboard host: `curl http://<host>:8100/api/v1/widget/summary`.

## 2. What the endpoint returns

`GET /api/v1/widget/summary?fit_min=65`

| Field | Meaning |
|---|---|
| `to_review` | Offers waiting for review: unread (minus the ones under "Set aside") plus updated. It is the number on the Inbox badge in the sidebar. |
| `to_review_high_fit` | Of those, the ones with a fit of `fit_min` or more (the threshold itself counts). Unscored offers never count. |
| `followed_recommended` | Of those, the ones from **followed companies** whose latest evaluation is *recommended*, whatever their fit. |
| `best_fit` | Highest fit among them (null if none is scored). |
| `status` | `ready` when the database and the worker are healthy, else `unavailable`. |
| `fit_threshold` | The `fit_min` that was used. |

Optional query parameters: `fit_min` (0-100, default 65) and `search_intent_id` (default: the first enabled intent, as in the inbox).

## 3. Add the service to `services.yaml`

Replace `<host>` with the address of the Jobs Radar host.

```yaml
- Jobs Radar:
    icon: mdi-radar
    href: http://<host>:5180
    description: Job-market radar
    siteMonitor: http://<host>:8100/readyz   # green when the database and worker are healthy
    widget:
      type: customapi
      url: http://<host>:8100/api/v1/widget/summary?fit_min=65
      refreshInterval: 60000
      mappings:
        - field: to_review_high_fit
          label: To review ≥ 65
          format: number
        - field: to_review
          label: To review in inbox
          format: number
        - field: followed_recommended
          label: Followed · recommended
          format: number
```

- **To review with fit ≥ 65:** `to_review_high_fit`. For another threshold change `fit_min` in the URL and the label (`fit_min=70` → "To review ≥ 70").
- **Total waiting in the inbox:** `to_review`, the same number as the Inbox badge in the sidebar (unread without the "Set aside" ones, plus updated).
- **Recommended offers of followed companies:** `followed_recommended`. Follow companies with the star in the Companies screen; the count only includes offers still waiting for review, so it drops when you read or dismiss them.
- **"Is Jobs Radar up?":** the `siteMonitor` line puts a green or red dot on the card. It turns red if the API, the database or the worker is down. To see it as text too, add `- field: status` / `label: Status` / `format: text` to `mappings`.

Homepage's `customapi` allows up to four mappings per widget; the three above leave room for `best_fit`. Reload the page after editing `services.yaml` (Homepage picks the change up on its own). If a value shows `-` or an error, open the `url` in a browser from the Homepage host to see the response.

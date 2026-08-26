# Capture bookmarklet — save an Upwork job with one click

A **zero-approval** way to get jobs into JobDesk today, without waiting for Upwork
API approval. Open an Upwork job page, click the bookmarklet, and the visible
posting is scraped and POSTed to `POST /api/capture`, where the
[`CaptureProvider`](../api/app/providers/capture.py) normalizes it to a
`source='capture'` job. Re-capturing the same posting updates it in place (it
dedupes on the Upwork job id in the URL — no duplicate rows).

Captured jobs land in the **Inbox** — no pipeline card is opened and nothing is
ever auto-applied. Promote a job to the pipeline yourself from the UI.

## Install (once)

1. Show your browser's bookmarks bar (Chrome/Edge: `Ctrl+Shift+B`).
2. Create a new bookmark (right-click the bar → **Add page…**). Name it
   `JobDesk: Capture`.
3. Paste the one-liner below as the **URL**, then **Save**.

> **Set your API port first.** The one-liner targets `http://localhost:8001`
> (this machine's `API_PORT`). If your `API_PORT` differs (the default is `8000`),
> change the `A=` value at the start of the bookmarklet to match.

```
javascript:(async()=>{const A='http://localhost:8001';const t=s=>(document.querySelector(s)?.textContent||'').trim();const T=document.body.innerText||'';const p={url:location.href,title:t('h1')||t('[data-test="job-title"]')||document.title.replace(/\s*[-|]\s*Upwork.*$/i,'').trim()||document.title,description:t('[data-test="Description"]')||t('[data-test="job-description-text"]')||t('[data-cy="description"]')||'',budget_type:/hourly/i.test(T)?'hourly':/fixed[- ]?price/i.test(T)?'fixed':null,workload:/less than 30 hrs\/week|part[- ]time/i.test(T)?'part_time':/more than 30 hrs\/week|full[- ]time/i.test(T)?'full_time':null,skills:[...document.querySelectorAll('[data-test="token"],[data-test="Skill"],.air3-token')].map(e=>e.textContent.trim()).filter(Boolean),captured_at:new Date().toISOString()};try{const r=await fetch(A+'/api/capture',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'omit',body:JSON.stringify(p)});const d=await r.json();if(!r.ok)throw new Error(d.detail||('HTTP '+r.status));alert('JobDesk: '+(d.created?'Captured':'Updated (already saved)')+'\n'+((d.jobs&&d.jobs[0]&&d.jobs[0].title)||p.title));}catch(e){alert('JobDesk capture failed: '+e.message+'\nIs the API running, and is '+location.origin+' in CORS_ORIGINS?');}})();
```

## Use

1. Open an Upwork job posting (`https://www.upwork.com/jobs/~0…`).
2. Click **JobDesk: Capture** in the bookmarks bar.
3. A small alert confirms `Captured` (new) or `Updated (already saved)` (dedupe).
   The job now shows in the JobDesk Inbox.

## Readable source

The one-liner above is this, minified. Scraping selectors are best-effort with
fallbacks — Upwork's DOM changes, so a miss just means a thinner posting (you can
always fill the rest in JobDesk, and the full page text is kept in `raw`).

```js
(async () => {
  const API_BASE = 'http://localhost:8001'; // match your API_PORT (.env)
  const t = (sel) => (document.querySelector(sel)?.textContent || '').trim();
  const pageText = document.body.innerText || '';

  const payload = {
    url: location.href,
    title:
      t('h1') ||
      t('[data-test="job-title"]') ||
      document.title.replace(/\s*[-|]\s*Upwork.*$/i, '').trim() ||
      document.title,
    description:
      t('[data-test="Description"]') ||
      t('[data-test="job-description-text"]') ||
      t('[data-cy="description"]') ||
      '',
    budget_type: /hourly/i.test(pageText) ? 'hourly'
               : /fixed[- ]?price/i.test(pageText) ? 'fixed'
               : null,
    workload: /less than 30 hrs\/week|part[- ]time/i.test(pageText) ? 'part_time'
            : /more than 30 hrs\/week|full[- ]time/i.test(pageText) ? 'full_time'
            : null,
    skills: [...document.querySelectorAll('[data-test="token"],[data-test="Skill"],.air3-token')]
      .map((e) => e.textContent.trim())
      .filter(Boolean),
    captured_at: new Date().toISOString(), // extra field — preserved in the job's raw
  };

  try {
    const res = await fetch(API_BASE + '/api/capture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'omit',
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'HTTP ' + res.status);
    const verb = data.created ? 'Captured' : 'Updated (already saved)';
    alert('JobDesk: ' + verb + '\n' + ((data.jobs?.[0]?.title) || payload.title));
  } catch (e) {
    alert('JobDesk capture failed: ' + e.message +
          '\nIs the API running, and is ' + location.origin + ' in CORS_ORIGINS?');
  }
})();
```

## How it maps to a job

The provider only trusts fields it can normalize and keeps the whole payload in
`raw` for later re-parsing:

| Scraped field | Becomes | Notes |
| --- | --- | --- |
| `url` | `url` (canonical) + `external_id` | Query/fragment stripped; `external_id` is the Upwork `~0…` job id (the dedupe key), falling back to the canonical URL. |
| `title` | `title` | Required. `document.title` is the last-resort source. |
| `budget_type` | `budget_type` | `hourly` / `fixed`; unrecognized wording is dropped. |
| `workload` | `workload` | `part_time` / `full_time` — feeds the part-time scope + AI match score. |
| `skills` | `skills` | Accepts an array or a comma/newline-separated string. |
| anything else | `raw` only | Untouched, for audit / re-parse later. |

## Why it works cross-origin (CORS & mixed content)

The bookmarklet runs on `https://www.upwork.com` and calls your local API — a
cross-origin request:

- **CORS:** `https://www.upwork.com` is in the API's allowed origins by default
  (see `CORS_ORIGINS` in `.env.example` and `app/config.py`). If you overrode
  `CORS_ORIGINS`, add `https://www.upwork.com` back or the browser blocks the call.
- **Mixed content:** Chrome/Edge/Firefox treat `http://localhost` (and
  `127.0.0.1`) as a secure context, so an `https://` page is allowed to call your
  local `http://localhost:PORT` API. No HTTPS or tunnel needed.
- The request sends no cookies (`credentials: 'omit'`) — this is a local,
  single-user tool.

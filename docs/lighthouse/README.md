# Lighthouse report — Low Bandwidth / Device Compatibility evidence

`signup-report.report.html` / `.json` is a real
[Lighthouse](https://developer.chrome.com/docs/lighthouse/) audit of
`/signup` (the page every role lands on, sharing the same base
layout/assets as the rest of the app), run with Lighthouse's default
**mobile form factor + simulated throttling** — a 4x CPU slowdown and a
throttled network profile, used as a stand-in for low-end-device and
low-bandwidth conditions since a real device/network lab isn't available.

## Results (2026-06-25)

| Category | Score |
|---|---|
| Performance | 92/100 |
| Accessibility | 96/100 |
| Best Practices | 100/100 |

| Metric | Value |
|---|---|
| First Contentful Paint | 2.6s |
| Largest Contentful Paint | 2.7s |
| Total Blocking Time | 0ms |
| Cumulative Layout Shift | 0 |
| Speed Index | 2.6s |

## How to reproduce

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 &
npx lighthouse http://127.0.0.1:8000/signup \
  --output html --output json \
  --output-path docs/lighthouse/signup-report \
  --only-categories=performance,accessibility,best-practices
```

These numbers reflect the self-hosted-assets + gzip-compression changes in
this same change set — re-run after any change to `static/` or `base.html`
to keep this report current.

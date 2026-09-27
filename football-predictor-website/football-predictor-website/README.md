# BetWise Predictor Website

A self-contained football prediction website with automatic match loading.

## What it does

- Loads fixtures automatically from public no-key feeds through the included backend.
- Enriches fixtures using previous results from the same feed where available.
- Predicts 1X2, BTTS, Over/Under, likely full-time score and half-time score lean.
- Generates fair odds, take-price gates, risk level, warnings and next actions.
- Builds a best-10 accumulator from loaded matches.
- Still supports manual single-match analysis when you want to override inputs.

## Data sources

The prototype uses public no-key fixture feeds:

- FixtureDownload JSON feeds for major leagues.
- TheSportsDB public daily soccer endpoint as a supplementary source.

Important: the odds shown from automatic fixtures are **model-generated odds**, not bookmaker prices. To use real prices, connect a licensed odds API later.

## Run locally

```bash
cd football-predictor-website
python3 server.py
```

Then open:

```text
http://localhost:8080
```

## API endpoint

```text
/api/fixtures?date=2026-09-27&days=7&league=all
```

Query parameters:

- `date`: start date in `YYYY-MM-DD`
- `days`: 1 to 31
- `league`: `all`, `top5`, or a feed slug such as `epl-2026`, `mls-2026`, `la-liga-2026`

## Legal/data note

This app is not affiliated with Forebet and does not scrape Forebet. It uses a Forebet-style statistical workflow with public fixture data and your own prediction logic.

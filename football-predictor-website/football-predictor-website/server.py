#!/usr/bin/env python3
"""Small local backend for BetWise Predictor.

It serves the static website and exposes /api/fixtures, which loads football
fixtures from public no-key feeds and enriches them with basic stats so the
front-end can predict matches without manual team input.
"""
from __future__ import annotations

import json
import math
import mimetypes
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (BetWise Predictor educational prototype)"
CACHE_TTL = 60 * 20
_CACHE: Dict[str, Tuple[float, Any]] = {}

FEEDS = {
    "epl-2026": "English Premier League",
    "championship-2026": "English Championship",
    "la-liga-2026": "Spanish LaLiga",
    "bundesliga-2026": "German Bundesliga",
    "serie-a-2026": "Italian Serie A",
    "ligue-1-2026": "French Ligue 1",
    "eredivisie-2026": "Dutch Eredivisie",
    "primeira-liga-2026": "Portuguese Primeira Liga",
    "scottish-premiership-2026": "Scottish Premiership",
    "mls-2026": "Major League Soccer",
    "champions-league-2026": "UEFA Champions League",
    "europa-league-2026": "UEFA Europa League",
}
GROUPS = {
    "all": list(FEEDS.keys()),
    "top5": ["epl-2026", "la-liga-2026", "bundesliga-2026", "serie-a-2026", "ligue-1-2026"],
}


def fetch_json(url: str) -> Any:
    now = time.time()
    cached = _CACHE.get(url)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[url] = (now, data)
    return data


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    value = value.replace("T", " ").replace("Z", "")
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def has_score(match: Dict[str, Any]) -> bool:
    return match.get("HomeTeamScore") is not None and match.get("AwayTeamScore") is not None


def score_pair(match: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    if not has_score(match):
        return None
    try:
        return int(match["HomeTeamScore"]), int(match["AwayTeamScore"])
    except Exception:
        return None


def result_char(team: str, match: Dict[str, Any]) -> Optional[str]:
    sp = score_pair(match)
    if not sp:
        return None
    hg, ag = sp
    if team == match.get("HomeTeam"):
        gf, ga = hg, ag
    elif team == match.get("AwayTeam"):
        gf, ga = ag, hg
    else:
        return None
    if gf > ga:
        return "W"
    if gf == ga:
        return "D"
    return "L"


def default_form() -> str:
    return "D-D-D-D-D"


def build_table(matches: List[Dict[str, Any]], before: datetime) -> Dict[str, Dict[str, float]]:
    table: Dict[str, Dict[str, float]] = {}
    for m in matches:
        dt = parse_dt(m.get("DateUtc", ""))
        if not dt or dt >= before:
            continue
        sp = score_pair(m)
        if not sp:
            continue
        home, away = m.get("HomeTeam"), m.get("AwayTeam")
        if not home or not away:
            continue
        hg, ag = sp
        for t in (home, away):
            table.setdefault(t, {"pts": 0, "gf": 0, "ga": 0, "p": 0})
        table[home]["p"] += 1
        table[away]["p"] += 1
        table[home]["gf"] += hg
        table[home]["ga"] += ag
        table[away]["gf"] += ag
        table[away]["ga"] += hg
        if hg > ag:
            table[home]["pts"] += 3
        elif hg < ag:
            table[away]["pts"] += 3
        else:
            table[home]["pts"] += 1
            table[away]["pts"] += 1
    return table


def ranks_from_table(table: Dict[str, Dict[str, float]], all_teams: Iterable[str]) -> Dict[str, int]:
    for t in all_teams:
        table.setdefault(t, {"pts": 0, "gf": 0, "ga": 0, "p": 0})
    ordered = sorted(table.items(), key=lambda kv: (kv[1]["pts"], kv[1]["gf"] - kv[1]["ga"], kv[1]["gf"]), reverse=True)
    return {team: idx + 1 for idx, (team, _) in enumerate(ordered)}


def team_matches(matches: List[Dict[str, Any]], team: str, before: datetime, homeaway: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    for m in matches:
        dt = parse_dt(m.get("DateUtc", ""))
        if not dt or dt >= before or not score_pair(m):
            continue
        if homeaway == "home" and m.get("HomeTeam") == team:
            out.append(m)
        elif homeaway == "away" and m.get("AwayTeam") == team:
            out.append(m)
        elif homeaway is None and (m.get("HomeTeam") == team or m.get("AwayTeam") == team):
            out.append(m)
    return sorted(out, key=lambda x: parse_dt(x.get("DateUtc", "")) or datetime.min.replace(tzinfo=timezone.utc))


def avg_gf_ga(team: str, matches: List[Dict[str, Any]], before: datetime, homeaway: Optional[str] = None) -> Tuple[float, float, int]:
    ms = team_matches(matches, team, before, homeaway)
    if not ms:
        return 1.35, 1.35, 0
    gf = ga = 0
    for m in ms:
        hg, ag = score_pair(m) or (0, 0)
        if m.get("HomeTeam") == team:
            gf += hg; ga += ag
        else:
            gf += ag; ga += hg
    n = len(ms)
    return gf / n, ga / n, n


def form_string(team: str, matches: List[Dict[str, Any]], before: datetime) -> str:
    ms = team_matches(matches, team, before)[-5:]
    chars = [result_char(team, m) for m in ms]
    chars = [c for c in chars if c]
    if not chars:
        return default_form()
    while len(chars) < 5:
        chars.insert(0, "D")
    return "-".join(chars[-5:])


def poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def xg_to_probs(hxg: float, axg: float) -> Tuple[float, float, float]:
    ph = pd = pa = total = 0.0
    for h in range(8):
        for a in range(8):
            p = poisson(h, hxg) * poisson(a, axg)
            total += p
            if h > a: ph += p
            elif h == a: pd += p
            else: pa += p
    return ph / total, pd / total, pa / total


def odds_from_probs(ph: float, pd: float, pa: float) -> Tuple[float, float, float]:
    # Add a small overround so the generated numbers behave like market odds.
    margin = 1.06
    return round(1 / max(ph * margin, 0.03), 2), round(1 / max(pd * margin, 0.03), 2), round(1 / max(pa * margin, 0.03), 2)


def enrich_fixture(match: Dict[str, Any], all_matches: List[Dict[str, Any]], league_name: str, slug: str) -> Optional[Dict[str, Any]]:
    dt = parse_dt(match.get("DateUtc", ""))
    home = match.get("HomeTeam")
    away = match.get("AwayTeam")
    if not dt or not home or not away:
        return None
    all_teams = set()
    for m in all_matches:
        if m.get("HomeTeam"): all_teams.add(m["HomeTeam"])
        if m.get("AwayTeam"): all_teams.add(m["AwayTeam"])
    table = build_table(all_matches, dt)
    ranks = ranks_from_table(table, all_teams)
    nteams = max(len(all_teams), 20)

    h_home_gf, h_home_ga, hhc = avg_gf_ga(home, all_matches, dt, "home")
    a_away_gf, a_away_ga, aac = avg_gf_ga(away, all_matches, dt, "away")
    h_all_gf, h_all_ga, hac = avg_gf_ga(home, all_matches, dt)
    a_all_gf, a_all_ga, aac2 = avg_gf_ga(away, all_matches, dt)

    home_gf = (h_home_gf * 0.62 + h_all_gf * 0.38) if hhc else h_all_gf
    home_ga = (h_home_ga * 0.62 + h_all_ga * 0.38) if hhc else h_all_ga
    away_gf = (a_away_gf * 0.62 + a_all_gf * 0.38) if aac else a_all_gf
    away_ga = (a_away_ga * 0.62 + a_all_ga * 0.38) if aac else a_all_ga

    # A lightweight odds estimate from the same stats. These are model odds, not bookmaker prices.
    hr = ranks.get(home, math.ceil(nteams / 2))
    ar = ranks.get(away, math.ceil(nteams / 2))
    rank_edge = ((nteams + 1 - hr) - (nteams + 1 - ar)) / max(nteams, 1)
    hxg = max(0.25, min(4.2, home_gf * 0.58 + away_ga * 0.42 + 0.22 + rank_edge * 0.18))
    axg = max(0.25, min(4.2, away_gf * 0.58 + home_ga * 0.42 - 0.06 - rank_edge * 0.15))
    ph, pd, pa = xg_to_probs(hxg, axg)
    ho, do, ao = odds_from_probs(ph, pd, pa)

    sp = score_pair(match)
    status = "finished" if sp else "scheduled"
    return {
        "id": f"{slug}-{match.get('MatchNumber', home + away)}",
        "source": "FixtureDownload",
        "league": league_name,
        "leagueSlug": slug,
        "dateUtc": match.get("DateUtc"),
        "venue": match.get("Location") or "",
        "round": match.get("RoundNumber"),
        "homeTeam": home,
        "awayTeam": away,
        "status": status,
        "score": {"home": sp[0], "away": sp[1]} if sp else None,
        "input": {
            "homeTeam": home,
            "awayTeam": away,
            "competition": league_name,
            "matchDate": dt.strftime("%Y-%m-%d"),
            "homeGF": round(home_gf, 2),
            "homeGA": round(home_ga, 2),
            "awayGF": round(away_gf, 2),
            "awayGA": round(away_ga, 2),
            "homeOdds": ho,
            "drawOdds": do,
            "awayOdds": ao,
            "homeForm": form_string(home, all_matches, dt),
            "awayForm": form_string(away, all_matches, dt),
            "homeRank": ranks.get(home, math.ceil(nteams / 2)),
            "awayRank": ranks.get(away, math.ceil(nteams / 2)),
            "leagueSize": nteams,
            "homeAdvantage": 0.25,
            "tempo": 1,
            "homeAttInj": 0,
            "awayAttInj": 0,
            "homeDefInj": 0,
            "awayDefInj": 0,
            "homeMotivation": 0,
            "awayMotivation": 0,
        },
    }


def thesportsdb_events(day: datetime) -> List[Dict[str, Any]]:
    date_s = day.strftime("%Y-%m-%d")
    url = f"https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={urllib.parse.quote(date_s)}&s=Soccer"
    data = fetch_json(url)
    events = data.get("events") or []
    out = []
    for e in events:
        home = e.get("strHomeTeam")
        away = e.get("strAwayTeam")
        ts = e.get("strTimestamp") or f"{e.get('dateEvent', date_s)}T{e.get('strTime', '00:00:00')}"
        dt = parse_dt(ts)
        if not home or not away or not dt:
            continue
        # Do not use final score in stats; this feed is only for auto fixture discovery.
        out.append({
            "id": f"tsdb-{e.get('idEvent')}",
            "source": "TheSportsDB",
            "league": e.get("strLeague") or "Soccer",
            "leagueSlug": "thesportsdb",
            "dateUtc": dt.strftime("%Y-%m-%d %H:%M:%SZ"),
            "venue": e.get("strVenue") or "",
            "round": e.get("intRound"),
            "homeTeam": home,
            "awayTeam": away,
            "status": "finished" if e.get("strStatus") == "FT" else "scheduled",
            "score": {"home": int(e["intHomeScore"]), "away": int(e["intAwayScore"])} if (e.get("intHomeScore") is not None and e.get("intAwayScore") is not None) else None,
            "input": {
                "homeTeam": home,
                "awayTeam": away,
                "competition": e.get("strLeague") or "Soccer",
                "matchDate": dt.strftime("%Y-%m-%d"),
                "homeGF": 1.35,
                "homeGA": 1.25,
                "awayGF": 1.20,
                "awayGA": 1.35,
                "homeOdds": 2.15,
                "drawOdds": 3.25,
                "awayOdds": 3.20,
                "homeForm": default_form(),
                "awayForm": default_form(),
                "homeRank": 10,
                "awayRank": 11,
                "leagueSize": 20,
                "homeAdvantage": 0.25,
                "tempo": 1,
                "homeAttInj": 0,
                "awayAttInj": 0,
                "homeDefInj": 0,
                "awayDefInj": 0,
                "homeMotivation": 0,
                "awayMotivation": 0,
            },
        })
    return out


def load_fixtures(start_date: str, days: int, league: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=days)
    slugs = GROUPS.get(league) or ([league] if league in FEEDS else GROUPS["all"])
    fixtures: List[Dict[str, Any]] = []
    errors: List[str] = []

    for slug in slugs:
        league_name = FEEDS[slug]
        url = f"https://fixturedownload.com/feed/json/{slug}"
        try:
            matches = fetch_json(url)
            if not isinstance(matches, list):
                continue
            for m in matches:
                dt = parse_dt(m.get("DateUtc", ""))
                if dt and start <= dt < end:
                    enriched = enrich_fixture(m, matches, league_name, slug)
                    if enriched:
                        fixtures.append(enriched)
        except Exception as exc:
            errors.append(f"{slug}: {exc}")

    # Supplement with TheSportsDB daily feed. Its free endpoint is small, but useful for U21/international fixtures.
    if league in ("all", "top5"):
        for offset in range(days):
            try:
                for item in thesportsdb_events(start + timedelta(days=offset)):
                    dt = parse_dt(item.get("dateUtc", ""))
                    if dt and start <= dt < end:
                        key = (item["homeTeam"].lower(), item["awayTeam"].lower(), item["dateUtc"][:10])
                        existing = {(f["homeTeam"].lower(), f["awayTeam"].lower(), f["dateUtc"][:10]) for f in fixtures}
                        if key not in existing:
                            fixtures.append(item)
            except Exception as exc:
                errors.append(f"TheSportsDB {offset}: {exc}")

    fixtures.sort(key=lambda f: (f.get("dateUtc") or "", f.get("league") or "", f.get("homeTeam") or ""))
    return fixtures, errors


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            return self.send_json({"ok": True, "timeUtc": datetime.now(timezone.utc).isoformat()})
        if parsed.path == "/api/fixtures":
            qs = urllib.parse.parse_qs(parsed.query)
            date = (qs.get("date") or [datetime.now(timezone.utc).strftime("%Y-%m-%d")])[0]
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return self.send_json({"error": "Invalid date; expected YYYY-MM-DD"}, 400)
            try:
                days = max(1, min(31, int((qs.get("days") or ["1"])[0])))
            except ValueError:
                days = 1
            league = (qs.get("league") or ["all"])[0]
            try:
                fixtures, errors = load_fixtures(date, days, league)
                return self.send_json({
                    "source": "FixtureDownload + TheSportsDB public feeds",
                    "date": date,
                    "days": days,
                    "league": league,
                    "count": len(fixtures),
                    "fixtures": fixtures,
                    "errors": errors,
                    "note": "Odds supplied here are generated model odds, not bookmaker odds. Connect a licensed odds API for live prices.",
                })
            except Exception as exc:
                return self.send_json({"error": str(exc)}, 500)

        # Static files
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    os.chdir(ROOT)
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"BetWise Predictor serving on http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server")

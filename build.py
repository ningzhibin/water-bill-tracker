#!/usr/bin/env python3
"""Build the water bill dashboard from the cleaned CSV.

Usage:
  1. extract bills from Gmail -> data/water-bills.csv
     (bill_date, amount_cad, due_date; one row per e-bill notification)
  2. python3 build.py        # regenerate docs/index.html from data/water-bills.csv
  3. push data/ + docs/ to GitHub (gh_api.py contents API)
"""
import csv, json, statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "water-bills.csv"
OUT = ROOT / "docs" / "index.html"

def load():
    recs = []
    with open(DATA) as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.strptime(r["bill_date"], "%Y-%m-%d").date()
                due = datetime.strptime(r["due_date"], "%Y-%m-%d").date()
            except ValueError:
                continue
            recs.append({
                "date": d.isoformat(), "amount": float(r["amount_cad"]),
                "due": due.isoformat(),
            })
    recs.sort(key=lambda x: x["date"])
    return recs

def main():
    recs = load()
    n = len(recs)
    amounts = [r["amount"] for r in recs]
    total = sum(amounts)
    avg = total / n

    # yearly averages
    yrs = {}
    for r in recs:
        yrs.setdefault(r["date"][:4], []).append(r["amount"])
    yrs_avg = {k: round(statistics.mean(v), 2) for k, v in sorted(yrs.items())}
    yrs_count = {k: len(v) for k, v in sorted(yrs.items())}

    # rolling 3-bill average for the trend line
    roll = []
    for i in range(len(amounts)):
        w = amounts[max(0, i - 2):i + 1]
        roll.append({"date": recs[i]["date"], "v": round(statistics.mean(w), 2)})

    # linear trend of amount vs time, $ per year (least squares on ordinal dates)
    xs = [datetime.strptime(r["date"], "%Y-%m-%d").toordinal() for r in recs]
    ys = amounts
    mx, my = statistics.mean(xs), statistics.mean(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    slope_yr = round(slope * 365.25, 2)

    payload = {
        "records": recs,
        "stats": {
            "bills": n,
            "span": f'{recs[0]["date"]} → {recs[-1]["date"]}',
            "total": round(total, 2),
            "avg": round(avg, 2),
            "latest": recs[-1]["amount"],
            "latest_due": recs[-1]["due"],
            "lowest": round(min(amounts), 2),
            "highest": round(max(amounts), 2),
            "slope_yr": slope_yr,
        },
        "yearly": yrs_avg, "yearly_count": yrs_count, "rolling": roll,
        "updated": datetime.now().strftime("%Y-%m-%d"),
    }

    html = HTML.replace("__PAYLOAD__", json.dumps(payload))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"wrote {OUT} ({len(html)//1024} KB), {n} bills")

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Water Bill Tracker — City of Ottawa</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
  body{font-family:-apple-system,system-ui,"Segoe UI",Roboto,sans-serif;max-width:980px;margin:0 auto;padding:20px;color:#222;background:#fafafa}
  h1{font-size:1.6em;margin-bottom:0} .sub{color:#666;margin:4px 0 20px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}
  .card{background:#fff;border:1px solid #e3e3e3;border-radius:10px;padding:12px 14px}
  .card .v{font-size:1.5em;font-weight:700} .card .l{color:#666;font-size:.85em}
  .chart{background:#fff;border:1px solid #e3e3e3;border-radius:10px;padding:14px;margin:18px 0}
  .chart h2{font-size:1.1em;margin:0 0 4px} .chart p{color:#666;font-size:.88em;margin:0 0 10px}
  canvas{max-height:340px}
  table{width:100%;border-collapse:collapse;font-size:.85em;background:#fff}
  th,td{padding:6px 8px;border-bottom:1px solid #eee;text-align:right}
  th:first-child,td:first-child{text-align:left}
  footer{color:#888;font-size:.8em;margin-top:24px}
  a{color:#1a73e8}
</style>
</head>
<body>
<h1>💧 Water Bill Tracker</h1>
<p class="sub">City of Ottawa water utility bills — every e-bill notification since Dec 2021. Pre-authorized debit; each bill covers about two months. Updated <span id="updated"></span>.</p>

<div class="cards" id="cards"></div>

<div class="chart"><h2>Amount per bill</h2>
<p>Each dot is one bi-monthly bill (CAD). The line is a 3-bill rolling average — trend: <b id="slope"></b> per year.</p>
<canvas id="c1"></canvas></div>

<div class="chart"><h2>Yearly averages</h2>
<p>Mean bill amount per calendar year.</p>
<canvas id="c2"></canvas></div>

<div class="chart"><h2>All bills</h2>
<table><thead><tr><th>Bill date</th><th>Amount (CAD)</th><th>Due date</th></tr></thead>
<tbody id="recent"></tbody></table></div>

<footer>Data: City of Ottawa e-bill notification emails (amount due + due date only — the emails do not include consumption in m³ or the water/sewer split; those live in the full bill on My ServiceOttawa). Account number intentionally not published. Analysis: automatic ·
<a href="https://github.com/ningzhibin/water-bill-tracker">Source &amp; raw CSV on GitHub</a></footer>

<script>
const D = __PAYLOAD__;
document.getElementById('updated').textContent = D.updated;
const s = D.stats;
const cards = [
  ['$' + s.latest.toFixed(2), 'latest bill, due ' + s.latest_due],
  ['$' + s.avg.toFixed(2), 'average per bill'],
  ['$' + s.total.toLocaleString(), 'total paid (' + s.bills + ' bills)'],
  [s.bills + ' bills', s.span],
  ['$' + s.lowest.toFixed(2) + ' – $' + s.highest.toFixed(2), 'lowest – highest'],
];
document.getElementById('cards').innerHTML = cards.map(c =>
  `<div class="card"><div class="v">${c[0]}</div><div class="l">${c[1]}</div></div>`).join('');
document.getElementById('slope').textContent = (s.slope_yr >= 0 ? '+$' : '−$') + Math.abs(s.slope_yr).toFixed(2);

const pts = D.records.map(r => ({x: r.date, y: r.amount}));
new Chart(document.getElementById('c1'), {type: 'scatter',
  data: {datasets: [
    {label: 'per bill', data: pts, pointRadius: 3, backgroundColor: '#1a73e880'},
    {label: '3-bill rolling avg', type: 'line', data: D.rolling.map(p => ({x: p.date, y: p.v})),
     borderColor: '#0288d1', borderWidth: 2, pointRadius: 0, tension: 0.2}]},
  options: {scales: {x: {type: 'time', time: {unit: 'year'}}, y: {title: {display: true, text: 'CAD'}}}, plugins: {legend: {display: true}}}});

const years = Object.keys(D.yearly);
new Chart(document.getElementById('c2'), {type: 'bar',
  data: {labels: years, datasets: [{data: years.map(k => D.yearly[k]),
    backgroundColor: '#4fc3f7'}]},
  options: {scales: {y: {title: {display: true, text: 'CAD'}}}, plugins: {legend: {display: false}}}});

document.getElementById('recent').innerHTML = D.records.slice().reverse().map(r =>
  `<tr><td>${r.date}</td><td>$${r.amount.toFixed(2)}</td><td>${r.due}</td></tr>`).join('');
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()

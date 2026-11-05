# Water Bill Tracker — 3714 RIVERBREEZE ST, Ottawa

Every City of Ottawa water utility e-bill for 3714 RIVERBREEZE ST, tracked since December 2021.

Dashboard: https://ningzhibin.github.io/water-bill-tracker/

## Data

`data/water-bills.csv` — one row per bill:

| column | meaning |
|---|---|
| `bill_date` | date of the e-bill notification email |
| `amount_cad` | amount due (CAD) |
| `due_date` | payment due date |

Source: City of Ottawa e-bill notification emails in Gmail. The emails carry only the amount due and due date — not consumption (m³) or the water/sewer split, which live in the full bill on My ServiceOttawa. The utility account number is intentionally not published here.

Bills are bi-monthly; payment is by pre-authorized debit.

## Update

1. Extract new bills from Gmail into `data/water-bills.csv`
2. `python3 build.py` — regenerates `docs/index.html`
3. Push `data/` + `docs/` to GitHub; the dashboard updates automatically (GitHub Pages, served from `docs/`).

Same setup as the [Ioniq fuel tracker](https://github.com/ningzhibin/ioniq-fuel-tracker).

## Auto-update

New bills are picked up automatically: a monthly check (15th, ~09:00 ET)
reads Gmail for new City of Ottawa e-bill notifications, appends them to
`data/water-bills.csv`, rebuilds the dashboard (`build.py`) and pushes both
files to GitHub (`update.py`). To update by hand: `python3 update.py`.

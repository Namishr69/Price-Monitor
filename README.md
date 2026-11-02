# Price Monitor Dashboard

A lightweight, self-hosted dashboard for tracking product prices across e-commerce sites. Add a product URL, and the dashboard visualizes price history, highlights trends, and surfaces at-a-glance stats, all in a clean dark/light-mode interface. A background job re-checks every tracked product automatically, so the history builds up on its own.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- **Live dashboard**: track products, view price history as an interactive line chart, and monitor system status at a glance
- **In-depth product stats**: per-product current/lowest/highest/average price, percent change since tracking began, and a mini trend sparkline
- **Dark / light mode**: toggle from the top bar; your preference is remembered between visits
- **Search & sort**: filter tracked products by name or URL, and sort by price or price change
- **Add / remove trackers**: paste a product URL to start monitoring, or delete a tracker and its history
- **Direct product links**: jump straight to the original product page from any tracked item
- **Automatic price checks**: every tracked product is re-scraped in the background every 4 hours
- **Works across retailers**: title and price are extracted generically (structured data first, then fallbacks), so there are no per-site selectors to write
- **Self-hosted data**: everything is stored in a local SQLite file, with no external services or accounts

## Tech Stack

**Frontend**
- HTML, CSS, and vanilla JavaScript (no framework, no build step)
- [Chart.js](https://www.chartjs.org/) for price history charts and sparklines
- [Google Material Symbols](https://fonts.google.com/icons) for iconography

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) served by Uvicorn
- SQLAlchemy with SQLite (`prices.db`, created automatically)
- APScheduler for the recurring background price checks
- Scraping with `curl_cffi`, Playwright (Chromium and Firefox), `playwright-stealth`, and BeautifulSoup

## Project Structure

```
├── index.html        # Dashboard page (add trackers, view chart, monitored items list)
├── products.html     # Products page (in-depth per-product stats)
├── styles.css        # Shared stylesheet (theme variables, layout, components)
├── script.js         # Dashboard page logic
├── products.js       # Products page logic
├── logo.png          # Site logo (plus favicon and apple-touch-icon files)
├── api.py            # FastAPI app: HTTP endpoints, scheduler startup, serves the frontend files
├── main.py           # check_all_prices(): the background job that re-scrapes every product
├── models.py         # Database engine, session factory, and tables (User, Product, PriceLog)
├── schemas.py        # Pydantic schemas for request/response validation
├── scraper.py        # scrape_product(): fetches a page and extracts title + price
└── prices.db         # SQLite database (auto-created on first run)
```

## Getting Started

You need Python 3.10+ and Git.

1. Clone the repo:
   ```bash
   git clone https://github.com/your-username/price-monitor-dashboard.git
   cd price-monitor-dashboard
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate          # Windows: venv\Scripts\activate
   ```
   Your prompt should show `(venv)`. Re-run the `source` line every time you open a new terminal.

3. Install dependencies:
   ```bash
   pip install fastapi "uvicorn[standard]" sqlalchemy apscheduler beautifulsoup4 curl_cffi playwright playwright-stealth
   ```

4. Download the browsers Playwright drives (one-time, about 200 MB):
   ```bash
   playwright install chromium firefox
   ```

5. Start the app:
   ```bash
   uvicorn api:app --reload
   ```

6. Open **http://127.0.0.1:8000** in your browser.

The backend also serves the frontend files, so there is nothing separate to host. The Products page is at **http://127.0.0.1:8000/products.html**.

### Running notes

- The format is `uvicorn <file>:<variable>`: `api` is `api.py`, and `app` is the `FastAPI()` instance inside it.
- On startup the app creates `prices.db` and its tables if they don't exist, runs one price check on every tracked product straight away, then repeats every 4 hours.
- `--reload` restarts the server whenever you save a file, and each restart triggers that startup price check again. For normal day-to-day use, run without it: `uvicorn api:app`.
- Stop the server with `Ctrl+C`.
- Interactive API docs are available at **http://127.0.0.1:8000/docs**.
- The frontend calls the API at `http://127.0.0.1:8000`. If your backend runs elsewhere (for example `--port 8001`), update `API_BASE` in `script.js` and `products.js`.
- Cross-origin requests are allowed, so you can also serve the frontend files from a separate static server (such as the VS Code Live Server extension) while the backend runs on port 8000.

## Usage

- **Add a tracker**: paste a product URL into the input on the Dashboard and click **Start Monitoring**.
- **View history**: click any item in the Monitored Items list to load its price chart.
- **View detailed stats**: head to the **Products** page for current/lowest/highest/average price, percent change, and a trend sparkline per item.
- **Search and sort**: filter by name or URL, and sort by price or price change.
- **Switch themes**: click the moon/sun icon in the top bar.
- **Remove a tracker**: click the trash icon on a product card.

New products start with a couple of data points so the chart can draw a line straight away. After that, a new point is logged every 4 hours.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/products` | List all tracked products |
| POST | `/products` | Add a product (`{ "url": "..." }`); scrapes it immediately |
| GET | `/products/{id}/history?limit=200` | Most recent price history for a product, oldest first (`[{ "price": 0, "checked_at": "ISO timestamp" }, ...]`) |
| DELETE | `/products/{id}` | Delete a product and its price history |

## How Scraping Works

`scrape_product()` tries three methods in order and stops at the first one that returns a title and price:

1. **Fast HTTP fetch** (`curl_cffi`, mimics Chrome's TLS fingerprint): quick, no JavaScript.
2. **Chromium with stealth patches** (Playwright): renders JavaScript-heavy pages.
3. **Firefox** (Playwright): a different automation fingerprint, which sometimes gets past bot protection that blocks Chromium.

Title and price are extracted in this order: JSON-LD structured data, microdata, Open Graph meta tags, common CSS class patterns, then a last-resort text scan. Unit prices like `$0.26 / 100g` and zero prices are filtered out.

Tested with JB Hi-Fi, PB Tech, Noel Leeming, Rebel Sport, Pak'nSave and books.toscrape.com. Sites with strong bot protection can still fail, and results can vary from product to product.

## Configuration

| What | Where |
|---|---|
| Check interval (default 4 hours) | `api.py`: `hours=4` in `scheduler.add_job(...)` |
| Sites to skip entirely | `scraper.py`: `EXCLUDED_DOMAINS` (currently `woolworths.co.nz`) |
| Database file location | `models.py`: `SQLALCHEMY_DATABASE_URL` |
| Backend address used by the frontend | `script.js` and `products.js`: `API_BASE` |

## Inspecting the Database

`sqlite3` ships with macOS, so you can look at the data directly:

```bash
sqlite3 prices.db ".tables"
sqlite3 prices.db "SELECT id, title, url FROM products;"
sqlite3 prices.db "SELECT COUNT(*) FROM price_logs;"
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | The virtual environment isn't active. Run `source venv/bin/activate`. |
| `Error loading ASGI app` / module not found | Run `uvicorn` from the project folder, and check the order: `api:app`, not `app:api`. |
| Dashboard loads but shows no products or a connection error | The backend isn't running, or `API_BASE` doesn't match the address it's running on. |
| `Executable doesn't exist` from Playwright | Run `playwright install chromium firefox`. |
| Product fails to add (400 error) | The site likely blocks scrapers or has no readable price. Check the terminal output to see which scraping step failed. |
| Port 8000 already in use | Stop the other process, or run `uvicorn api:app --port 8001` and update `API_BASE`. |
| Tab icon missing in Safari | Safari caches favicons aggressively and may show a tab count badge in compact tab layouts. It works in Chrome and Firefox, and doesn't affect the app. |

## Roadmap

- [ ] Alerts page: notify when a tracked price drops below a threshold
- [ ] Analytics page: aggregate trends across all tracked products

## Notes

- Scraping is intended for personal use. Keep the check interval reasonable so you don't hammer retailer sites.
- `prices.db` is created locally and holds all your data. Back it up if you care about the history.

## License

This project is licensed under the MIT License. Feel free to use and modify it for your own projects.

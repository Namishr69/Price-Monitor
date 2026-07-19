# Price Monitor Dashboard

A lightweight, self-hosted dashboard for tracking product prices across e-commerce sites. Add a product URL, and the dashboard visualizes price history, highlights trends, and surfaces at-a-glance stats — all in a clean, dark/light-mode interface.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- **Live dashboard** — track products, view price history as an interactive line chart, and monitor system status at a glance
- **In-depth product stats** — per-product current/lowest/highest/average price, percent change since tracking began, and a mini trend sparkline
- **Dark / light mode** — toggle from the top bar; your preference is remembered between visits
- **Search & sort** — filter tracked products by name or URL, and sort by price or price change
- **Add / remove trackers** — paste a product URL to start monitoring, or delete a tracker and its history
- **Direct product links** — jump straight to the original product page from any tracked item

## Tech Stack

**Frontend**
- HTML, CSS, and vanilla JavaScript (no framework, no build step)
- [Chart.js](https://www.chartjs.org/) for price history charts and sparklines
- [Google Material Symbols](https://fonts.google.com/icons) for iconography

**Backend** *(not included in this repo — connect your own)*
- Expects a REST API at `http://127.0.0.1:8000` with the following endpoints:
  - `GET /products` — list tracked products
  - `POST /products` — add a new product (`{ "url": "..." }`)
  - `DELETE /products/{id}` — remove a tracked product
  - `GET /products/{id}/history` — price history log for a product (`[{ "price": 0, "checked_at": "ISO timestamp" }, ...]`)

## Project Structure

```
├── index.html       # Dashboard page (add trackers, view chart, monitored items list)
├── products.html     # Products page (in-depth per-product stats)
├── styles.css        # Shared stylesheet (theme variables, layout, components)
├── script.js         # Dashboard page logic
├── products.js        # Products page logic
└── logo.png          # Site logo
```

## Getting Started

1. Clone the repo:
   ```bash
   git clone https://github.com/your-username/price-monitor-dashboard.git
   cd price-monitor-dashboard
   ```

2. Make sure your backend API is running at `http://127.0.0.1:8000` (update `API_BASE` in `script.js` and `products.js` if your backend runs elsewhere).

3. Open `index.html` in your browser — no build step or server required for the frontend.

   > Tip: for local development, serving the folder with a simple static server (e.g. `npx serve` or the VS Code Live Server extension) avoids any browser quirks with `file://` URLs.

## Usage

- **Add a tracker**: paste a product URL into the input on the Dashboard and click **Start Monitoring**.
- **View history**: click any item in the Monitored Items list to load its price chart.
- **View detailed stats**: head to the **Products** page for current/lowest/highest/average price, percent change, and a trend sparkline per item.
- **Switch themes**: click the moon/sun icon in the top bar.
- **Remove a tracker**: click the trash icon on a product card.

## Roadmap

- [ ] Alerts page — notify when a tracked price drops below a threshold
- [ ] Analytics page — aggregate trends across all tracked products

## License

This project is licensed under the MIT License — feel free to use and modify it for your own projects.

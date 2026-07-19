/* ============================================
   SETTINGS
   ============================================ */

   const API_BASE = "http://127.0.0.1:8000";

   // Keep the full list around so we can re-sort/filter without re-fetching
   let allProductsWithStats = [];
   
   // Track sparkline chart instances so we can clean them up if we re-render
   let sparklineCharts = [];
   
   /* ============================================
      DARK / LIGHT MODE SWITCHER
      (same behaviour as the dashboard page)
      ============================================ */
   
   const themeToggleBtn = document.getElementById("themeToggleBtn");
   const themeIcon = document.getElementById("themeIcon");
   
   function applyTheme(theme) {
       if (theme === "light") {
           document.body.classList.add("light-mode");
           themeIcon.textContent = "light_mode";
       } else {
           document.body.classList.remove("light-mode");
           themeIcon.textContent = "dark_mode";
       }
   }
   
   const savedTheme = localStorage.getItem("theme") || "dark";
   applyTheme(savedTheme);
   
   themeToggleBtn.addEventListener("click", () => {
       const isLight = document.body.classList.contains("light-mode");
       const newTheme = isLight ? "dark" : "light";
       applyTheme(newTheme);
       localStorage.setItem("theme", newTheme);
       renderProductCards(allProductsWithStats); // redraw sparklines with matching colors
   });
   
   /* ============================================
      SEARCH / FILTER
      ============================================ */
   
   document.getElementById("searchBox").addEventListener("input", (event) => {
       const searchTerm = event.target.value.toLowerCase();
       const allCards = document.querySelectorAll(".product-detail-card");
   
       allCards.forEach((card) => {
           const title = card.getAttribute("data-title").toLowerCase();
           const url = card.getAttribute("data-url").toLowerCase();
           const matches = title.includes(searchTerm) || url.includes(searchTerm);
           card.style.display = matches ? "grid" : "none";
       });
   });
   
   /* ============================================
      SORTING
      ============================================ */
   
   document.getElementById("sortSelect").addEventListener("change", (event) => {
       const sorted = sortProducts(allProductsWithStats, event.target.value);
       renderProductCards(sorted);
   });
   
   function sortProducts(products, sortBy) {
       const copy = [...products];
   
       switch (sortBy) {
           case "price-high":
               return copy.sort((a, b) => (b.stats.current ?? 0) - (a.stats.current ?? 0));
           case "price-low":
               return copy.sort((a, b) => (a.stats.current ?? 0) - (b.stats.current ?? 0));
           case "change":
               return copy.sort((a, b) => Math.abs(b.stats.percentChange ?? 0) - Math.abs(a.stats.percentChange ?? 0));
           case "name":
               return copy.sort((a, b) => a.title.localeCompare(b.title));
           case "recent":
           default:
               return copy.sort((a, b) => b.id - a.id);
       }
   }
   
   /* ============================================
      LOAD PRODUCTS + THEIR HISTORY, THEN COMPUTE STATS
      ============================================ */
   
   async function loadProductStats() {
       const listContainer = document.getElementById("productsDetailList");
   
       try {
           const response = await fetch(`${API_BASE}/products`);
           const products = await response.json();
   
           if (products.length === 0) {
               listContainer.innerHTML = `
                   <div class="empty-page-state">
                       <span class="material-symbols-outlined empty-icon">inbox</span>
                       <p><strong>No products tracked yet</strong></p>
                       <p>Add a product from the Dashboard to see its stats here.</p>
                   </div>`;
               return;
           }
   
           // Fetch price history for every product in parallel
           const productsWithStats = await Promise.all(
               products.map(async (product) => {
                   const history = await fetchHistory(product.id);
                   return {
                       ...product,
                       history: history,
                       stats: computeStats(history)
                   };
               })
           );
   
           allProductsWithStats = productsWithStats;
   
           const sortSelect = document.getElementById("sortSelect");
           const sorted = sortProducts(productsWithStats, sortSelect.value);
           renderProductCards(sorted);
   
       } catch (error) {
           console.error("Error loading product stats:", error);
           listContainer.innerHTML = `
               <div class="empty-page-state">
                   <span class="material-symbols-outlined empty-icon">error</span>
                   <p>Error connecting to server.</p>
                   <p>Is the FastAPI backend running?</p>
               </div>`;
       }
   }
   
   async function fetchHistory(productId) {
       try {
           const response = await fetch(`${API_BASE}/products/${productId}/history`);
           if (!response.ok) return [];
           return await response.json();
       } catch (error) {
           console.error(`Error fetching history for product ${productId}:`, error);
           return [];
       }
   }
   
   /* ============================================
      COMPUTE STATS FROM A PRODUCT'S PRICE HISTORY
      ============================================ */
   
   function computeStats(history) {
       if (!history || history.length === 0) {
           return {
               current: null,
               lowest: null,
               highest: null,
               average: null,
               percentChange: null,
               checksLogged: 0,
               lastChecked: null
           };
       }
   
       const prices = history.map((entry) => entry.price);
       const first = prices[0];
       const current = prices[prices.length - 1];
       const lowest = Math.min(...prices);
       const highest = Math.max(...prices);
       const average = prices.reduce((sum, price) => sum + price, 0) / prices.length;
       const percentChange = first === 0 ? 0 : ((current - first) / first) * 100;
       const lastChecked = history[history.length - 1].checked_at;
   
       return {
           current,
           lowest,
           highest,
           average,
           percentChange,
           checksLogged: history.length,
           lastChecked
       };
   }
   
   /* ============================================
      RENDER PRODUCT DETAIL CARDS
      ============================================ */
   
   function renderProductCards(products) {
       const listContainer = document.getElementById("productsDetailList");
       listContainer.innerHTML = "";
   
       // Clean up old sparkline charts before drawing new ones
       sparklineCharts.forEach((chart) => chart.destroy());
       sparklineCharts = [];
   
       products.forEach((product) => {
           const card = buildProductDetailCard(product);
           listContainer.appendChild(card);
   
           if (product.history && product.history.length > 1) {
               const canvas = card.querySelector(".sparkline-canvas");
               const chart = drawSparkline(canvas, product.history);
               sparklineCharts.push(chart);
           }
       });
   }
   
   function buildProductDetailCard(product) {
       const stats = product.stats;
       const card = document.createElement("div");
       card.className = "product-detail-card";
       card.setAttribute("data-title", product.title);
       card.setAttribute("data-url", product.url);
   
       card.innerHTML = `
           <div class="product-detail-identity">
               <p class="product-detail-title">${product.title}${buildChangeBadge(stats.percentChange)}</p>
               <p class="product-detail-url">${product.url}</p>
               <div class="product-detail-meta">
                   <span><span class="material-symbols-outlined">history</span> ${stats.checksLogged} price check${stats.checksLogged === 1 ? "" : "s"} logged</span>
                   <span><span class="material-symbols-outlined">schedule</span> Last checked: ${formatLastChecked(stats.lastChecked)}</span>
               </div>
               <a href="${product.url}" target="_blank" rel="noopener noreferrer" class="link-btn">
                   Link
                   <span class="material-symbols-outlined">open_in_new</span>
               </a>
           </div>
   
           <div class="product-stat-pills">
               ${buildStatPill("Current", stats.current)}
               ${buildStatPill("Lowest", stats.lowest)}
               ${buildStatPill("Highest", stats.highest)}
               ${buildStatPill("Average", stats.average)}
           </div>
   
           <div class="product-sparkline-box">
               ${
                   product.history && product.history.length > 1
                       ? `<canvas class="sparkline-canvas"></canvas>`
                       : `<div class="no-history-note">Not enough data yet<br>for a trend line</div>`
               }
           </div>
       `;
   
       return card;
   }
   
   function buildStatPill(label, value) {
       const displayValue = value === null || value === undefined
           ? "—"
           : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
   
       return `
           <div class="stat-pill">
               <p class="stat-pill-label">${label}</p>
               <p class="stat-pill-value">${displayValue}</p>
           </div>
       `;
   }
   
   function buildChangeBadge(percentChange) {
       if (percentChange === null || percentChange === undefined || Math.abs(percentChange) < 0.01) {
           return `<span class="change-badge neutral"><span class="material-symbols-outlined">remove</span>No change</span>`;
       }
   
       const isPositive = percentChange > 0;
       const iconName = isPositive ? "trending_up" : "trending_down";
       const badgeClass = isPositive ? "positive" : "negative";
       const sign = isPositive ? "+" : "";
   
       return `<span class="change-badge ${badgeClass}"><span class="material-symbols-outlined">${iconName}</span>${sign}${percentChange.toFixed(1)}%</span>`;
   }
   
   function formatLastChecked(rawDate) {
       if (!rawDate) return "Never";
       const dateString = rawDate.endsWith("Z") ? rawDate : rawDate + "Z";
       const date = new Date(dateString);
       const datePart = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
       const timePart = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
       return `${datePart}, ${timePart}`;
   }
   
   /* ============================================
      DRAW A SMALL SPARKLINE CHART FOR A PRODUCT
      ============================================ */
   
   function drawSparkline(canvas, history) {
       const prices = history.map((entry) => entry.price);
       const isLight = document.body.classList.contains("light-mode");
   
       const ctx = canvas.getContext("2d");
       const gradient = ctx.createLinearGradient(0, 0, 0, 90);
       gradient.addColorStop(0, "rgba(56, 189, 248, 0.3)");
       gradient.addColorStop(1, "rgba(56, 189, 248, 0)");
   
       return new Chart(ctx, {
           type: "line",
           data: {
               labels: prices.map((_, index) => index),
               datasets: [{
                   data: prices,
                   borderColor: "#0ea5e9",
                   backgroundColor: gradient,
                   borderWidth: 2,
                   pointRadius: 0,
                   tension: 0.35,
                   fill: true
               }]
           },
           options: {
               responsive: true,
               maintainAspectRatio: false,
               plugins: {
                   legend: { display: false },
                   tooltip: {
                       callbacks: {
                           title: () => "",
                           label: (context) => new Intl.NumberFormat("en-US", {
                               style: "currency",
                               currency: "USD"
                           }).format(context.parsed.y)
                       }
                   }
               },
               scales: {
                   x: { display: false },
                   y: { display: false }
               }
           }
       });
   }
   
   /* ============================================
      START
      ============================================ */
   
   loadProductStats();
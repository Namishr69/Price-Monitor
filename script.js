/* ============================================
   SETTINGS
   ============================================ */

   const API_BASE = "http://127.0.0.1:8000";

   // Keeps track of the currently drawn chart so we can
   // destroy it before drawing a new one.
   let priceChart = null;
   
   /* ============================================
      DARK / LIGHT MODE SWITCHER
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
   
   // Load saved theme preference (defaults to dark mode)
   const savedTheme = localStorage.getItem("theme") || "dark";
   applyTheme(savedTheme);
   
   themeToggleBtn.addEventListener("click", () => {
       const isLight = document.body.classList.contains("light-mode");
       const newTheme = isLight ? "dark" : "light";
       applyTheme(newTheme);
       localStorage.setItem("theme", newTheme);
   });
   
   /* ============================================
      SEARCH / FILTER PRODUCTS
      ============================================ */
   
   document.getElementById("searchBox").addEventListener("input", (event) => {
       const searchTerm = event.target.value.toLowerCase();
       const allCards = document.querySelectorAll(".product-card");
   
       allCards.forEach((card) => {
           const title = card.getAttribute("data-title").toLowerCase();
           const url = card.getAttribute("data-url").toLowerCase();
           const matches = title.includes(searchTerm) || url.includes(searchTerm);
           card.style.display = matches ? "flex" : "none";
       });
   });
   
   /* ============================================
      LOAD PRODUCTS FROM THE API
      ============================================ */
   
   async function loadProducts(selectedProductId = null) {
       const listContainer = document.getElementById("productsList");
   
       try {
           const response = await fetch(`${API_BASE}/products`);
           const products = await response.json();
   
           // Update the stat cards at the top
           document.getElementById("statTracked").textContent = products.length || 0;
           document.getElementById("statMonitors").textContent = products.length || 0;
   
           listContainer.innerHTML = "";
   
           if (products.length === 0) {
               listContainer.innerHTML = `
                   <div class="empty-state">
                       <span class="material-symbols-outlined empty-icon">inbox</span>
                       <p><strong>No trackers active</strong></p>
                       <p>Add a product URL above to start monitoring.</p>
                   </div>`;
               resetChart();
               return;
           }
   
           products.forEach((product, index) => {
               const card = buildProductCard(product);
               listContainer.appendChild(card);
   
               // Decide which card should be auto-selected
               const shouldAutoSelect = selectedProductId
                   ? product.id === selectedProductId
                   : index === 0;
   
               if (shouldAutoSelect) {
                   selectProductCard(card, product);
               }
           });
   
       } catch (error) {
           console.error("Error fetching products:", error);
           listContainer.innerHTML = `
               <div class="empty-state">
                   <span class="material-symbols-outlined empty-icon">error</span>
                   <p>Error connecting to server.</p>
                   <p>Is the FastAPI backend running?</p>
               </div>`;
       }
   }
   
   // Builds a single product card element
   function buildProductCard(product) {
       const card = document.createElement("div");
       card.className = "product-card";
       card.setAttribute("data-title", product.title);
       card.setAttribute("data-url", product.url);
   
       card.innerHTML = `
           <div class="product-info">
               <p class="product-title">${product.title}</p>
               <p class="product-url">${product.url}</p>
           </div>
           <button class="delete-btn" title="Delete tracker">
               <span class="material-symbols-outlined">delete</span>
           </button>
       `;
   
       // Clicking the card selects it and loads its price history
       card.addEventListener("click", () => {
           selectProductCard(card, product);
       });
   
       // Clicking delete removes it (without triggering the card click above)
       const deleteButton = card.querySelector(".delete-btn");
       deleteButton.addEventListener("click", (event) => {
           event.stopPropagation();
           deleteProduct(product.id);
       });
   
       return card;
   }
   
   // Highlights the selected card and loads its chart data
   function selectProductCard(card, product) {
       document.querySelectorAll(".product-card").forEach((c) => {
           c.classList.remove("selected");
       });
       card.classList.add("selected");
   
       loadPriceHistory(product.id, product.title);
   
       // Scroll it into view nicely
       setTimeout(() => {
           card.scrollIntoView({ behavior: "smooth", block: "center" });
       }, 100);
   }
   
   /* ============================================
      LOAD & DRAW PRICE HISTORY CHART
      ============================================ */
   
   async function loadPriceHistory(productId, title) {
       const chartTitle = document.getElementById("chartTitle");
       const chartSubtitle = document.getElementById("chartSubtitle");
   
       chartTitle.textContent = title;
       chartSubtitle.textContent = "Historical entry analysis and timeline.";
   
       try {
           const response = await fetch(`${API_BASE}/products/${productId}/history`);
   
           if (!response.ok) {
               chartSubtitle.textContent = `Couldn't load history (server returned ${response.status}).`;
               return;
           }
   
           const logs = await response.json();
   
           if (logs.length === 0) {
               chartSubtitle.textContent = "No price checks logged yet — awaiting next scheduled sync.";
               resetChart();
               return;
           }
   
           if (logs.length === 1) {
               chartSubtitle.textContent = "Initial datapoint recorded. Line will form upon next check.";
           }
   
           drawChart(logs);
   
       } catch (error) {
           console.error("Error loading historical trends:", error);
           chartSubtitle.textContent = "Analytics rendering error. Check console for details.";
       }
   }
   
   function drawChart(logs) {
       const labels = logs.map((log) => formatLogDate(log.checked_at));
       const prices = logs.map((log) => log.price);
   
       if (priceChart) {
           priceChart.destroy();
       }
   
       const canvas = document.getElementById("priceChart");
       const ctx = canvas.getContext("2d");
   
       // Soft gradient fill under the line
       const gradient = ctx.createLinearGradient(0, 0, 0, 400);
       gradient.addColorStop(0, "rgba(56, 189, 248, 0.35)");
       gradient.addColorStop(1, "rgba(56, 189, 248, 0)");
   
       const isLight = document.body.classList.contains("light-mode");
       Chart.defaults.color = isLight ? "#64748b" : "#94a3b8";
   
       priceChart = new Chart(ctx, {
           type: "line",
           data: {
               labels: labels,
               datasets: [{
                   label: "Price ($)",
                   data: prices,
                   borderColor: "#0ea5e9",
                   backgroundColor: gradient,
                   borderWidth: 2,
                   pointBackgroundColor: isLight ? "#ffffff" : "#0f172a",
                   pointBorderColor: "#0ea5e9",
                   pointBorderWidth: 2,
                   pointRadius: 4,
                   pointHoverRadius: 6,
                   tension: 0.35,
                   fill: true
               }]
           },
           options: {
               responsive: true,
               maintainAspectRatio: false,
               interaction: { mode: "index", intersect: false },
               plugins: {
                   legend: { display: false },
                   tooltip: {
                       callbacks: {
                           label: (context) => {
                               const value = context.parsed.y;
                               return `Price: ${new Intl.NumberFormat("en-US", {
                                   style: "currency",
                                   currency: "USD"
                               }).format(value)}`;
                           }
                       }
                   }
               },
               scales: {
                   x: { ticks: { maxTicksLimit: 6 } },
                   y: {
                       ticks: {
                           callback: (value) => `$${value}`
                       }
                   }
               }
           }
       });
   }
   
   function resetChart() {
       if (priceChart) {
           priceChart.destroy();
           priceChart = null;
       }
       document.getElementById("chartTitle").textContent = "Price History Trend";
       document.getElementById("chartSubtitle").textContent =
           "Select an item on the left to review its timeline data.";
   }
   
   // Turns an ISO date string into something readable, e.g. "Jul 19, 3:45 PM"
   function formatLogDate(rawDate) {
       const dateString = rawDate.endsWith("Z") ? rawDate : rawDate + "Z";
       const date = new Date(dateString);
       const datePart = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
       const timePart = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
       return `${datePart} ${timePart}`;
   }
   
   /* ============================================
      DELETE A PRODUCT
      ============================================ */
   
   function deleteProduct(productId) {
       if (!productId) {
           alert("No product selected to delete!");
           return;
       }
   
       const confirmed = confirm("Remove this tracker and permanently delete its history?");
       if (!confirmed) return;
   
       fetch(`${API_BASE}/products/${productId}`, { method: "DELETE" })
           .then((response) => {
               if (response.ok) {
                   loadProducts();
               } else {
                   alert("Failed to delete product from database.");
               }
           })
           .catch((error) => console.error("Error deleting product:", error));
   }
   
   /* ============================================
      ADD A NEW PRODUCT (FORM SUBMIT)
      ============================================ */
   
   const addProductForm = document.getElementById("addProductForm");
   const formMessage = document.getElementById("formMessage");
   
   addProductForm.addEventListener("submit", async (event) => {
       event.preventDefault();
   
       const urlInput = document.getElementById("productUrlInput");
   
       showFormMessage("loading", "hourglass_empty", "Analyzing source metadata...");
   
       try {
           const response = await fetch(`${API_BASE}/products`, {
               method: "POST",
               headers: { "Content-Type": "application/json" },
               body: JSON.stringify({ url: urlInput.value })
           });
   
           if (response.ok) {
               const newProduct = await response.json();
               showFormMessage("success", "check_circle", "Successfully added to tracking!");
               urlInput.value = "";
               loadProducts(newProduct.id);
   
               // Hide the success message after a few seconds
               setTimeout(() => hideFormMessage(), 4000);
           } else {
               const errorData = await response.json();
               showFormMessage("error", "error", `Error: ${errorData.detail || "Failed to parse URL"}`);
           }
       } catch (error) {
           showFormMessage("error", "error", "Connection failed. Ensure backend is active.");
       }
   });
   
   function showFormMessage(type, iconName, text) {
       formMessage.className = `form-message show ${type}`;
       formMessage.innerHTML = `<span class="material-symbols-outlined">${iconName}</span> ${text}`;
   }
   
   function hideFormMessage() {
       formMessage.classList.remove("show");
   }
   
   /* ============================================
      START THE APP
      ============================================ */
   
   loadProducts();
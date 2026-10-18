/* Vendor dashboard behaviour. */
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ---------- Mobile sidebar ---------- */
  const sidebar = $("#dashSidebar");
  const backdrop = $(".dash-backdrop");
  function setSidebar(open) {
    sidebar?.classList.toggle("open", open);
    backdrop?.classList.toggle("show", open);
  }
  $("[data-sidebar-toggle]")?.addEventListener("click", () => setSidebar(true));
  backdrop?.addEventListener("click", () => setSidebar(false));
  document.addEventListener("keydown", (e) => e.key === "Escape" && setSidebar(false));

  /* ---------- Product form ---------- */
  const productForm = $("[data-product-form]");
  if (productForm) {
    const maxImages = parseInt(productForm.dataset.maxImages, 10);
    const minImages = parseInt(productForm.dataset.minImages, 10);
    const currency = productForm.dataset.currency;
    const grid = $("[data-image-grid]");
    const input = $("[data-image-input]");
    const dropzone = $("[data-dropzone]");
    const countEl = $("[data-image-count]");
    const errorEl = $("[data-image-error]");
    const primaryInput = productForm.querySelector("input[name=primary_image]");
    let newFiles = [];

    const keptExisting = () => $$("[data-existing-image]").filter((tile) => !tile.querySelector("[data-remove-image]").checked);
    const totalImages = () => keptExisting().length + newFiles.length;

    function showError(message) {
      errorEl.textContent = message || "";
      errorEl.hidden = !message;
    }

    function markPrimary(value) {
      primaryInput.value = value;
      $$(".image-tile", grid).forEach((tile) => {
        const isPrimary = tile.dataset.primaryValue === value;
        tile.classList.toggle("is-primary", isPrimary);
        tile.querySelector(".primary-flag")?.remove();
        if (isPrimary) {
          const flag = document.createElement("span");
          flag.className = "primary-flag";
          flag.textContent = "Primary";
          tile.prepend(flag);
        }
      });
    }

    function syncInputFiles() {
      const dt = new DataTransfer();
      newFiles.forEach((f) => dt.items.add(f));
      input.files = dt.files;
    }

    function renderNewTiles() {
      $$("[data-new-image]", grid).forEach((t) => t.remove());
      newFiles.forEach((file, index) => {
        const tile = document.createElement("div");
        tile.className = "image-tile";
        tile.dataset.newImage = index;
        tile.dataset.primaryValue = `new-${index}`;
        const img = document.createElement("img");
        img.alt = file.name;
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        const actions = document.createElement("div");
        actions.className = "tile-actions";
        actions.innerHTML =
          `<button type="button" data-make-primary="new-${index}"><i class="bi bi-star"></i> Primary</button>` +
          `<button type="button" data-remove-new="${index}"><i class="bi bi-x-lg"></i> Remove</button>`;
        tile.append(img, actions);
        grid.appendChild(tile);
      });
      updateCount();
    }

    function updateCount() {
      const total = totalImages();
      countEl.textContent = total;
      dropzone.classList.toggle("opacity-50", total >= maxImages);
      if (total > maxImages) showError(`You can upload at most ${maxImages} images. Remove ${total - maxImages}.`);
      else showError("");
    }

    function addFiles(fileList) {
      const allowed = ["image/jpeg", "image/png", "image/webp"];
      const rejected = [];
      for (const file of fileList) {
        if (!allowed.includes(file.type)) { rejected.push(`${file.name} (unsupported type)`); continue; }
        if (file.size > 5 * 1024 * 1024) { rejected.push(`${file.name} (over 5 MB)`); continue; }
        if (totalImages() >= maxImages) { rejected.push(`${file.name} (limit of ${maxImages} reached)`); continue; }
        newFiles.push(file);
      }
      syncInputFiles();
      renderNewTiles();
      if (rejected.length) showError(`Skipped: ${rejected.join(", ")}`);
    }

    $$("[data-existing-image]").forEach((tile) => { tile.dataset.primaryValue = `existing-${tile.dataset.existingImage}`; });

    input.addEventListener("change", () => {
      const picked = Array.from(input.files);
      syncInputFiles(); // reset to tracked files, then append the new picks
      addFiles(picked);
    });
    ["dragenter", "dragover"].forEach((evt) => dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("is-dragover"); }));
    ["dragleave", "drop"].forEach((evt) => dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("is-dragover"); }));
    dropzone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

    grid.addEventListener("click", (e) => {
      const primaryBtn = e.target.closest("[data-make-primary]");
      if (primaryBtn) { markPrimary(primaryBtn.dataset.makePrimary); return; }
      const removeNew = e.target.closest("[data-remove-new]");
      if (removeNew) {
        const index = parseInt(removeNew.dataset.removeNew, 10);
        if (primaryInput.value === `new-${index}`) primaryInput.value = "";
        newFiles.splice(index, 1);
        syncInputFiles();
        renderNewTiles();
      }
    });
    grid.addEventListener("change", (e) => {
      const box = e.target.closest("[data-remove-image]");
      if (!box) return;
      const tile = box.closest(".image-tile");
      tile.classList.toggle("is-removed", box.checked);
      tile.querySelector("label span").textContent = box.checked ? "Undo" : "Remove";
      updateCount();
    });
    $$("[data-remove-image]:checked").forEach((box) => box.dispatchEvent(new Event("change", { bubbles: true })));

    productForm.addEventListener("submit", (e) => {
      const total = totalImages();
      if (total < minImages || total > maxImages) {
        e.preventDefault();
        showError(total < minImages ? `Add at least ${minImages} image${minImages > 1 ? "s" : ""}.` : `Maximum ${maxImages} images.`);
        dropzone.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });

    /* Live price preview */
    const priceInput = productForm.querySelector("input[name=price]");
    const discountInput = productForm.querySelector("input[name=discount_percent]");
    const preview = $("[data-price-preview]");
    const money = (n) => `${currency} ${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
    const num = (name) => Math.max(parseFloat(productForm.querySelector(`input[name=${name}]`)?.value) || 0, 0);
    const costOut = {
      unit: $("[data-unit-cost]"),
      profit: $("[data-unit-profit]"),
      margin: $("[data-margin]"),
    };
    function updatePrice() {
      const price = parseFloat(priceInput.value);
      const discount = Math.min(Math.max(parseInt(discountInput.value || "0", 10) || 0, 0), 90);
      const final = price > 0 ? Math.round(price * (100 - discount)) / 100 : 0;
      preview.textContent = final ? money(final) + (discount ? ` (−${discount}%)` : "") : "–";

      if (!costOut.unit) return;
      const cost = num("purchase_cost") + num("inbound_shipping_cost") + num("other_cost");
      costOut.unit.textContent = money(cost);
      if (!final) { costOut.profit.textContent = costOut.margin.textContent = "–"; return; }
      const profit = final - cost;
      costOut.profit.textContent = money(profit);
      costOut.margin.textContent = `${((profit / final) * 100).toFixed(1)}%`;
      costOut.profit.closest("div").classList.toggle("is-loss", profit < 0);
    }
    productForm.addEventListener("input", (e) => {
      if (["price", "discount_percent", "purchase_cost", "inbound_shipping_cost", "other_cost"].includes(e.target.name)) updatePrice();
    });
    updatePrice();
  }

  /* ---------- Show a field only for one chosen status (e.g. amount when completing) ---------- */
  $$("[data-show-for-status]").forEach((block) => {
    const form = block.closest("form");
    const input = block.querySelector("input");
    const sync = () => {
      const chosen = form.querySelector("input[name=status]:checked, select[name=status]")?.value;
      const show = chosen === block.dataset.showForStatus;
      block.hidden = !show;
      input.required = show;
    };
    form.addEventListener("change", sync);
    sync();
  });

  /* ---------- Date range: preset vs custom dates are mutually exclusive ---------- */
  $$(".date-range").forEach((range) => {
    const preset = range.querySelector("[data-date-preset]");
    const customs = $$("[data-date-custom]", range);
    customs.forEach((input) =>
      input.addEventListener("change", () => {
        preset.value = "";
        input.form.requestSubmit();
      })
    );
    preset.addEventListener("change", () => customs.forEach((input) => (input.value = "")), { capture: true });
  });

  /* ---------- Finance chart: revenue & cost columns + net-profit line ---------- */
  const chartEl = $("[data-viz-chart]");
  const chartData = (() => {
    try { return JSON.parse($("#viz-trend-data")?.textContent || "[]"); } catch (_) { return []; }
  })();
  if (chartEl && chartData.length) {
    const SVG_NS = "http://www.w3.org/2000/svg";
    const svg = $("svg", chartEl);
    const tip = $(".viz-tooltip", chartEl);
    const symbol = chartEl.dataset.currency || "";
    const MINUS = "−";

    const money = (v) => `${v < 0 ? MINUS : ""}${symbol} ${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    const compact = (v) => {
      const a = Math.abs(v);
      const body = a >= 1e6 ? `${+(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `${+(a / 1e3).toFixed(0)}K` : `${a}`;
      return `${v < 0 ? MINUS : ""}${body}`;
    };
    const el = (name, attrs = {}, parent = svg) => {
      const node = document.createElementNS(SVG_NS, name);
      Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
      parent.appendChild(node);
      return node;
    };
    const niceStep = (span, ticks) => {
      const raw = span / ticks || 1;
      const mag = 10 ** Math.floor(Math.log10(raw));
      return [1, 2, 2.5, 5, 10].map((x) => x * mag).find((s) => raw <= s);
    };
    // Column with a 4px rounded data-end and a square baseline.
    const column = (x, base, top, w) => {
      const h = base - top;
      if (h <= 0.5) return "";
      const r = Math.min(4, h, w / 2);
      return `M${x},${base}V${top + r}Q${x},${top} ${x + r},${top}H${x + w - r}Q${x + w},${top} ${x + w},${top + r}V${base}Z`;
    };

    let activeIndex = -1;
    let layout = null;

    function render() {
      const width = chartEl.clientWidth;
      const narrow = width < 520;
      const height = narrow ? 240 : 300;
      const m = { top: 22, right: 16, bottom: 30, left: narrow ? 44 : 70 };
      const plotW = width - m.left - m.right;
      const plotH = height - m.top - m.bottom;
      svg.innerHTML = "";
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.setAttribute("width", width);
      svg.setAttribute("height", height);

      // Scale always includes zero and extends below it when a month made a loss.
      const values = chartData.flatMap((d) => [d.revenue, d.costs, d.net]);
      const rawMax = Math.max(0, ...values);
      const rawMin = Math.min(0, ...values);
      const step = niceStep(rawMax - rawMin, narrow ? 3 : 4);
      const top = Math.max(Math.ceil(rawMax / step) * step, step);
      const bottom = Math.floor(rawMin / step) * step;
      const y = (v) => m.top + ((top - v) / (top - bottom)) * plotH;
      const y0 = y(0);

      const grid = el("g");
      for (let v = bottom; v <= top + step / 2; v += step) {
        el("line", { x1: m.left, x2: width - m.right, y1: y(v), y2: y(v), class: Math.abs(v) < 1e-9 ? "viz-zero" : "viz-grid" }, grid);
        const t = el("text", { x: m.left - 10, y: y(v), class: "viz-tick", "text-anchor": "end", "dominant-baseline": "middle" }, grid);
        // Narrow screens drop the currency symbol on the axis; the summary above shows it.
        const unit = narrow ? "" : `${symbol} `;
        t.textContent = Math.abs(v) < 1e-9 ? "0" : `${v < 0 ? MINUS : ""}${unit}${compact(Math.abs(v))}`;
      }

      const band = plotW / chartData.length;
      const barW = Math.max(4, Math.min(24, (band - Math.max(10, band * 0.3) - 2) / 2));
      const labelEvery = band < 46 ? 2 : 1;
      const centers = chartData.map((_, i) => m.left + band * i + band / 2);

      // Hover highlight sits under the marks.
      const hover = el("rect", { class: "viz-band", x: 0, y: m.top - 8, width: band, height: plotH + 8, rx: 8, opacity: 0 });

      const bars = el("g", { class: "viz-bars" });
      chartData.forEach((d, i) => {
        const cx = centers[i];
        el("path", { d: column(cx - 1 - barW, y0, y(d.revenue), barW), class: "viz-col s1" }, bars);
        el("path", { d: column(cx + 1, y0, y(d.costs), barW), class: "viz-col s2" }, bars);
        if (i % labelEvery === (chartData.length - 1) % labelEvery) {
          el("text", { x: cx, y: height - 8, class: "viz-tick", "text-anchor": "middle" }).textContent = d.label;
        }
      });

      // Net-profit line with surface-ringed markers.
      const pts = chartData.map((d, i) => [centers[i], y(d.net)]);
      el("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(""), class: "viz-line s3" });
      const dots = el("g");
      pts.forEach((p) => el("circle", { cx: p[0], cy: p[1], r: 4, class: "viz-dot s3" }, dots));

      // Selective direct label: the latest net value only.
      const last = chartData.length - 1;
      // Sits just left of the last dot, on the side away from the incoming line segment
      // (and never above the plot's top edge).
      const [lx, ly] = pts[last];
      const label = el("text", { x: lx - 10, y: ly, class: "viz-direct", "text-anchor": "end", "dominant-baseline": "middle" });
      label.textContent = `Net ${money(chartData[last].net)}`;
      // Height of the incoming segment at the label's far (left) edge.
      const labelLeft = lx - 10 - label.getBBox().width;
      const [px, py] = last > 0 ? pts[last - 1] : [lx, ly];
      const segmentY = px < lx ? ly + ((py - ly) * (lx - Math.max(labelLeft, px))) / (lx - px) : ly;
      const roomBelow = Math.max(ly, segmentY) + 26 < m.top + plotH;
      // Below the line when there's room, otherwise above both the point and the segment.
      const labelY = roomBelow ? Math.max(ly, segmentY) + 16 : Math.min(ly, segmentY) - 12;
      label.setAttribute("y", Math.max(labelY, m.top + 6));

      // Whole-month hit targets, keyboard focusable.
      const hits = el("g");
      chartData.forEach((d, i) => {
        const hit = el("rect", {
          x: m.left + band * i, y: m.top - 8, width: band, height: plotH + m.bottom + 8,
          class: "viz-hit", tabindex: 0, role: "button",
          "aria-label": `${d.title}: revenue ${money(d.revenue)}, costs ${money(d.costs)}, net ${money(d.net)}`,
        }, hits);
        const show = () => showTip(i);
        hit.addEventListener("mouseenter", show);
        hit.addEventListener("focus", show);
        hit.addEventListener("click", show);
      });

      layout = { hover, band, m, centers };
      if (activeIndex >= 0) showTip(activeIndex);
    }

    function addRow(key, label, value, extra = "") {
      const r = document.createElement("div");
      r.className = `viz-tip-row ${extra}`.trim();
      const name = document.createElement("span");
      if (key) {
        const k = document.createElement("i");
        k.className = key;
        name.appendChild(k);
      }
      name.append(label);
      const val = document.createElement("span");
      val.textContent = value;
      r.append(name, val);
      tip.appendChild(r);
    }

    function showTip(i) {
      activeIndex = i;
      const { hover, band, m, centers } = layout;
      const d = chartData[i];
      hover.setAttribute("x", m.left + band * i + 2);
      hover.setAttribute("width", Math.max(band - 4, 0));
      hover.setAttribute("opacity", 1);
      tip.innerHTML = "";
      const title = document.createElement("strong");
      title.textContent = d.title;
      tip.appendChild(title);
      addRow("viz-swatch s1", "Revenue", money(d.revenue));
      addRow("viz-swatch s2", "Costs", money(d.costs));
      addRow("", "Cost of goods", money(d.cogs), "is-sub");
      addRow("", "Expenses", money(d.expenses), "is-sub");
      addRow("viz-linekey", d.net < 0 ? "Net loss" : "Net profit", money(d.net), "is-net");
      if (d.net_pct !== null && d.net_pct !== undefined) {
        const change = document.createElement("div");
        change.className = "viz-tip-change";
        const badge = document.createElement("span");
        badge.className = `delta ${d.net_good === true ? "is-good" : d.net_good === false ? "is-bad" : ""}`;
        const arrow = document.createElement("i");
        arrow.className = `bi ${d.net_pct > 0 ? "bi-arrow-up-short" : d.net_pct < 0 ? "bi-arrow-down-short" : "bi-dash"}`;
        badge.append(arrow, `${Math.abs(d.net_pct).toFixed(1)}%`);
        change.append(badge, " net vs previous month");
        tip.appendChild(change);
      }
      tip.hidden = false;
      // Open beside the hovered month so its columns stay visible: right if it fits, else left.
      const gap = 10;
      const bandLeft = m.left + band * i;
      const right = bandLeft + band + gap;
      const fitsRight = right + tip.offsetWidth <= chartEl.clientWidth;
      const left = fitsRight ? right : Math.max(bandLeft - gap - tip.offsetWidth, 0);
      tip.style.left = `${left}px`;
      tip.style.top = `${m.top}px`;
    }

    function hideTip() {
      activeIndex = -1;
      tip.hidden = true;
      layout?.hover.setAttribute("opacity", 0);
    }

    chartEl.addEventListener("mouseleave", hideTip);
    chartEl.addEventListener("focusout", (e) => { if (!chartEl.contains(e.relatedTarget)) hideTip(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });

    let frame;
    new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(render);
    }).observe(chartEl);
    render();
    // Bars grow in on first paint only; later re-renders (resize) are instant.
    setTimeout(() => svg.classList.add("is-static"), 700);
  }

  /* ---------- Stock adjustment modal ---------- */
  const adjustModal = $("#adjustModal");
  if (adjustModal) {
    const form = $("[data-adjust-form]", adjustModal);
    const qty = form.querySelector("input[name=quantity]");
    const preview = $("[data-adjust-preview]", adjustModal);
    const reason = form.querySelector("select[name=reason]");
    let current = 0;

    function updatePreview() {
      const mode = form.querySelector("input[name=mode]:checked").value;
      const n = parseInt(qty.value, 10);
      if (Number.isNaN(n)) { preview.textContent = "–"; return; }
      const next = mode === "add" ? current + n : mode === "remove" ? current - n : n;
      preview.textContent = next < 0 ? "Not enough stock" : next;
      preview.classList.toggle("text-danger", next < 0);
    }

    adjustModal.addEventListener("show.bs.modal", (e) => {
      const trigger = e.relatedTarget;
      form.action = trigger.dataset.adjustUrl;
      current = parseInt(trigger.dataset.productStock, 10);
      $("[data-adjust-name]", adjustModal).textContent = trigger.dataset.productName;
      $("[data-adjust-stock]", adjustModal).textContent = current;
      form.reset();
      updatePreview();
    });
    adjustModal.addEventListener("shown.bs.modal", () => qty.focus());
    form.addEventListener("input", updatePreview);
    form.addEventListener("change", (e) => {
      if (e.target.name !== "mode") return;
      reason.value = e.target.value === "add" ? "restock" : e.target.value === "remove" ? "damaged" : "correction";
      updatePreview();
    });
  }
})();

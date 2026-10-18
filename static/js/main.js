/* HairClub storefront behaviour. Progressive enhancement: every feature here
   has a server-rendered fallback, so the site works without JavaScript. */
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ---------- Light / dark theme ---------- */
  // The initial theme is set by an inline script in <head>; this wires up the
  // toggle. An explicit choice is remembered, otherwise we follow the OS.
  const THEME_KEY = "hc-theme";
  const root = document.documentElement;
  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const storedTheme = () => {
    try { return localStorage.getItem(THEME_KEY); } catch (_) { return null; }
  };

  function applyTheme(theme) {
    // Suppress per-component transitions so the whole page switches at once.
    root.classList.add("theme-switching");
    root.setAttribute("data-bs-theme", theme);
    $$("[data-theme-toggle]").forEach((btn) => {
      btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      btn.title = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
      btn.hidden = false;
    });
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove("theme-switching")));
  }

  applyTheme(root.getAttribute("data-bs-theme") === "dark" ? "dark" : "light");
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-theme-toggle]")) return;
    const next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    try { localStorage.setItem(THEME_KEY, next); } catch (_) { /* private mode */ }
    applyTheme(next);
  });
  darkQuery.addEventListener("change", (e) => {
    if (!storedTheme()) applyTheme(e.matches ? "dark" : "light");
  });

  /* ---------- Toasts ---------- */
  const toastStack = $("#toastStack");

  function dismiss(toast) {
    toast.style.transition = "opacity 200ms";
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 220);
  }

  function showToast(message, isError = false) {
    if (!toastStack) return;
    const toast = document.createElement("div");
    toast.className = "hc-toast" + (isError ? " error" : "");
    toast.setAttribute("role", "status");
    const icon = document.createElement("i");
    icon.className = "bi " + (isError ? "bi-exclamation-octagon-fill" : "bi-check-circle-fill");
    const text = document.createElement("div");
    text.className = "flex-grow-1";
    text.textContent = message;
    toast.append(icon, text);
    toastStack.appendChild(toast);
    setTimeout(() => dismiss(toast), 4000);
  }

  $$("[data-autohide]").forEach((t) => setTimeout(() => dismiss(t), 5000));
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-dismiss-toast]");
    if (btn) dismiss(btn.closest(".hc-toast"));
  });

  function setBadge(selector, count) {
    $$(selector).forEach((el) => {
      el.dataset.count = count;
      el.textContent = count > 0 ? count : "";
    });
  }

  async function postForm(form) {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
      credentials: "same-origin",
    });
    let data = {};
    try { data = await response.json(); } catch (_) { /* non-JSON error page */ }
    return { response, data };
  }

  /* ---------- AJAX add to cart ---------- */
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest("[data-cart-form]");
    if (!form) return;
    e.preventDefault();
    const button = form.querySelector("[type=submit]");
    button && (button.disabled = true);
    try {
      const { response, data } = await postForm(form);
      if (data.cart_count !== undefined) setBadge("[data-cart-count]", data.cart_count);
      showToast(data.message || (response.ok ? "Added to cart." : "Could not add to cart."), !response.ok);
    } catch (_) {
      form.submit();
    } finally {
      button && (button.disabled = false);
    }
  });

  /* ---------- Wishlist toggle ---------- */
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest("[data-wishlist-form]");
    if (!form) return;
    e.preventDefault();
    try {
      const { response, data } = await postForm(form);
      if (response.status === 401 && data.login_url) {
        window.location.href = data.login_url;
        return;
      }
      if (!response.ok) throw new Error();
      $$(`[data-wishlist-form][action="${form.getAttribute("action")}"] .wishlist-btn`).forEach((btn) => {
        btn.classList.toggle("is-active", data.in_wishlist);
        btn.setAttribute("aria-pressed", data.in_wishlist ? "true" : "false");
      });
      setBadge("[data-wishlist-count]", data.wishlist_count);
      showToast(data.message);
      if (!data.in_wishlist && form.dataset.removeCard !== undefined) {
        form.closest("[data-card]")?.remove();
      }
    } catch (_) {
      form.submit();
    }
  });

  /* ---------- Quantity steppers ---------- */
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-qty-step]");
    if (!btn) return;
    const input = btn.closest(".qty-stepper").querySelector("input");
    const step = parseInt(btn.dataset.qtyStep, 10);
    const min = parseInt(input.min || "0", 10);
    const max = parseInt(input.max || "999", 10);
    const next = Math.min(max, Math.max(min, (parseInt(input.value, 10) || 0) + step));
    input.value = next;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  $$("[data-autosubmit]").forEach((input) =>
    input.addEventListener("change", () => input.form && input.form.requestSubmit())
  );

  $$("[data-filter-toggle]").forEach((box) =>
    box.addEventListener("change", () => { window.location.href = box.checked ? box.dataset.on : box.dataset.off; })
  );

  /* ---------- Product gallery ---------- */
  const mainImage = $("[data-gallery-main]");
  if (mainImage) {
    $$("[data-gallery-thumb]").forEach((thumb) =>
      thumb.addEventListener("click", () => {
        mainImage.src = thumb.dataset.full;
        mainImage.alt = thumb.dataset.alt || mainImage.alt;
        $$("[data-gallery-thumb]").forEach((t) => t.classList.remove("active"));
        thumb.classList.add("active");
      })
    );
  }

  /* ---------- Booking: live slot loading ---------- */
  const bookingForm = $("[data-booking-form]");
  if (bookingForm) {
    const dateInput = bookingForm.querySelector("input[name=date]");
    const timeSelect = bookingForm.querySelector("select[name=time]");
    const hint = $("[data-slot-hint]");
    const slotsUrl = bookingForm.dataset.slotsUrl;

    async function loadSlots() {
      if (!dateInput.value) return;
      const previous = timeSelect.value;
      timeSelect.disabled = true;
      timeSelect.innerHTML = '<option value="">Loading times…</option>';
      try {
        const res = await fetch(`${slotsUrl}?date=${encodeURIComponent(dateInput.value)}`, {
          headers: { Accept: "application/json" },
        });
        const data = await res.json();
        const available = (data.slots || []).filter((s) => s.available);
        timeSelect.innerHTML = "";
        const placeholder = new Option(available.length ? "Select a time" : "No times available", "");
        timeSelect.add(placeholder);
        (data.slots || []).forEach((slot) => {
          const opt = new Option(slot.available ? slot.label : `${slot.label} (fully booked)`, slot.value);
          opt.disabled = !slot.available;
          timeSelect.add(opt);
        });
        if (available.some((s) => s.value === previous)) timeSelect.value = previous;
        if (hint) {
          hint.textContent = data.message || `${available.length} time${available.length === 1 ? "" : "s"} available`;
          hint.classList.toggle("text-danger", !available.length);
        }
      } catch (_) {
        timeSelect.innerHTML = '<option value="">Could not load times. Please try again.</option>';
      } finally {
        timeSelect.disabled = false;
      }
    }
    dateInput.addEventListener("change", loadSlots);
    if (dateInput.value && timeSelect.options.length <= 1) loadSlots();
  }

  /* ---------- Checkout: live shipping total ---------- */
  const checkout = $("[data-checkout]");
  if (checkout) {
    const subtotal = parseFloat(checkout.dataset.subtotal);
    const symbol = checkout.dataset.currency;
    const shippingEl = $("[data-shipping-amount]");
    const totalEl = $("[data-total-amount]");
    const addressBlock = $("[data-address-block]");
    const bankInfo = $("[data-bank-info]");
    const fmt = (n) => `${symbol} ${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;

    function refresh() {
      const shipping = checkout.querySelector("input[name=shipping_method]:checked");
      if (shipping) {
        const cost = parseFloat(shipping.dataset.cost || "0");
        shippingEl.textContent = cost > 0 ? fmt(cost) : "Free";
        totalEl.textContent = fmt(subtotal + cost);
        if (addressBlock) addressBlock.hidden = shipping.value === "pickup";
      }
      const payment = checkout.querySelector("input[name=payment_method]:checked");
      if (bankInfo) bankInfo.hidden = !payment || payment.value !== "bank_transfer";
    }
    checkout.addEventListener("change", refresh);
    refresh();
  }

  /* ---------- Appointment booked: forward to WhatsApp ---------- */
  const forward = $("[data-whatsapp-forward]");
  if (forward) {
    let seconds = parseInt(forward.dataset.seconds || "4", 10);
    const counter = $("[data-countdown]");
    const timer = setInterval(() => {
      seconds -= 1;
      if (counter) counter.textContent = Math.max(seconds, 0);
      if (seconds <= 0) {
        clearInterval(timer);
        window.location.href = forward.href;
      }
    }, 1000);
    $("[data-cancel-forward]")?.addEventListener("click", () => {
      clearInterval(timer);
      $("[data-forward-note]")?.remove();
    });
  }

  /* ---------- Confirm destructive actions ---------- */
  document.addEventListener("submit", (e) => {
    const form = e.target.closest("form[data-confirm]");
    if (form && !window.confirm(form.dataset.confirm)) e.preventDefault();
  });
})();

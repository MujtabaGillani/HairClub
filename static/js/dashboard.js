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
    function updatePrice() {
      const price = parseFloat(priceInput.value);
      const discount = Math.min(Math.max(parseInt(discountInput.value || "0", 10) || 0, 0), 90);
      if (!price || price <= 0) { preview.textContent = "–"; return; }
      const final = Math.round(price * (100 - discount)) / 100;
      preview.textContent = `${currency} ${final.toLocaleString("en-US", { maximumFractionDigits: 2 })}` + (discount ? ` (−${discount}%)` : "");
    }
    priceInput.addEventListener("input", updatePrice);
    discountInput.addEventListener("input", updatePrice);
    updatePrice();
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

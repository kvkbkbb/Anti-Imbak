/* Anti-Imbak — progressive enhancement for the marketplace. */
(() => {
  "use strict";

  document.documentElement.classList.add("js");

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const peso = new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    minimumFractionDigits: 2,
  });

  const money = (value) => {
    const number = Number(value);
    return Number.isFinite(number) ? peso.format(number) : "₱0.00";
  };

  /* ---------------------------------------------------------------------
     Header, mobile navigation and toasts
     --------------------------------------------------------------------- */
  const header = $("[data-site-header]");
  if (header) {
    const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  const menu = $("[data-mobile-menu]");
  const menuToggle = $("[data-menu-toggle]");
  const menuClose = $("[data-menu-close]");
  const menuScrim = $("[data-menu-scrim]");
  let lastFocused = null;

  const setMenu = (open, restoreFocus = true) => {
    if (!menu) return;
    menu.classList.toggle("is-open", open);
    menu.setAttribute("aria-hidden", String(!open));
    document.body.classList.toggle("menu-open", open);
    if (menuToggle) menuToggle.setAttribute("aria-expanded", String(open));
    if (open) {
      lastFocused = document.activeElement;
      window.setTimeout(() => {
        const first = menu.querySelector("a, button");
        if (first) first.focus();
      }, 60);
    } else if (restoreFocus && lastFocused instanceof HTMLElement) {
      lastFocused.focus();
    }
  };

  menuToggle?.addEventListener("click", () => setMenu(!menu?.classList.contains("is-open")));
  menuClose?.addEventListener("click", () => setMenu(false));
  menuScrim?.addEventListener("click", () => setMenu(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu?.classList.contains("is-open")) setMenu(false);
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 1024 && menu?.classList.contains("is-open")) setMenu(false, false);
  });

  const removeToast = (toast) => {
    if (!toast || toast.classList.contains("is-leaving")) return;
    toast.classList.add("is-leaving");
    window.setTimeout(() => toast.remove(), 240);
  };

  $$("[data-toast]").forEach((toast) => {
    const close = $("[data-toast-close]", toast);
    close?.addEventListener("click", () => removeToast(toast));
    window.setTimeout(() => removeToast(toast), 7000);
  });

  /* ---------------------------------------------------------------------
     Native dialogs
     --------------------------------------------------------------------- */
  const closeDialog = (dialog) => {
    if (!dialog) return;
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    else dialog.removeAttribute("open");
    document.body.classList.toggle("modal-open", $$("dialog[open]").length > 0);
  };

  $$("[data-dialog-open]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      const dialog = document.getElementById(trigger.dataset.dialogOpen);
      if (!dialog) return;
      if (typeof dialog.showModal === "function") {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
      document.body.classList.add("modal-open");
      const focusTarget = dialog.querySelector("textarea, input, select, button");
      if (focusTarget) {
        window.setTimeout(() => focusTarget.focus(), 80);
      }
    });
  });

  $$("dialog").forEach((dialog) => {
    if (dialog.tagName.toLowerCase() !== "dialog") return;
    $$("[data-dialog-close]", dialog).forEach((button) => {
      button.addEventListener("click", () => closeDialog(dialog));
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog(dialog);
    });
    dialog.addEventListener("close", () => {
      document.body.classList.toggle("modal-open", $$("dialog[open]").length > 0);
    });
  });

  // Allow server-rendered deep links (for example ?claim=1) to open a dialog
  // without inline scripts, which the Content Security Policy forbids.
  $$("dialog[data-auto-open='true']").forEach((dialog) => {
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    document.body.classList.add("modal-open");
    const focusTarget = dialog.querySelector("textarea, input, select");
    if (focusTarget) {
      window.setTimeout(() => focusTarget.focus(), 120);
    }
  });

  /* ---------------------------------------------------------------------
     Confirmations for destructive actions
     --------------------------------------------------------------------- */
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const submitter = event.submitter;
    const message = (submitter instanceof HTMLElement && submitter.dataset.confirm) || form.dataset.confirm;
    if (message && !window.confirm(message)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  });

  /* ---------------------------------------------------------------------
     Listing gallery
     --------------------------------------------------------------------- */
  const galleryMain = $("#gallery-main-image");
  const galleryThumbs = $$("[data-gallery-thumb]");
  if (galleryMain && galleryThumbs.length) {
    let activeIndex = Math.max(0, galleryThumbs.findIndex((thumb) => thumb.classList.contains("is-current")));
    const counter = $("[data-gallery-current]");

    const showImage = (index) => {
      activeIndex = (index + galleryThumbs.length) % galleryThumbs.length;
      const thumb = galleryThumbs[activeIndex];
      galleryMain.src = thumb.dataset.src || galleryMain.src;
      if (thumb.dataset.alt) galleryMain.alt = thumb.dataset.alt;
      galleryThumbs.forEach((item, itemIndex) => {
        item.classList.toggle("is-current", itemIndex === activeIndex);
        item.setAttribute("aria-current", itemIndex === activeIndex ? "true" : "false");
      });
      if (counter) counter.textContent = String(activeIndex + 1);
    };

    galleryThumbs.forEach((thumb, index) => {
      thumb.addEventListener("click", () => showImage(index));
    });
    $("[data-gallery-prev]")?.addEventListener("click", () => showImage(activeIndex - 1));
    $("[data-gallery-next]")?.addEventListener("click", () => showImage(activeIndex + 1));

    document.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const tag = document.activeElement?.tagName;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
      if (!$(".detail-gallery")) return;
      event.preventDefault();
      showImage(activeIndex + (event.key === "ArrowRight" ? 1 : -1));
    });
  }

  /* ---------------------------------------------------------------------
     Upload previews and drag + drop
     --------------------------------------------------------------------- */
  const previewRootFor = (input) =>
    input.closest("[data-upload-zone]") ||
    input.closest(".avatar-edit") ||
    input.closest(".form-section") ||
    document;

  const renderImageFiles = (input) => {
    const root = previewRootFor(input);
    const preview = $("[data-image-preview]", root);
    if (!preview) return;
    const files = Array.from(input.files || []).filter((file) => file.type.startsWith("image/"));
    preview.innerHTML = "";
    preview.classList.toggle("has-files", files.length > 0);

    files.slice(0, 5).forEach((file, index) => {
      const figure = document.createElement("figure");
      figure.className = "upload-thumb";
      const image = document.createElement("img");
      image.alt = `Selected photo ${index + 1}`;
      image.loading = "lazy";
      const objectUrl = URL.createObjectURL(file);
      image.src = objectUrl;
      image.addEventListener("load", () => URL.revokeObjectURL(objectUrl), { once: true });
      const label = document.createElement("figcaption");
      label.textContent = `${Math.round(file.size / 1024)} KB`;
      figure.append(image, label);
      preview.append(figure);
    });

    if (files.length > 5) {
      const note = document.createElement("p");
      note.className = "upload-limit-note";
      note.textContent = `Only the first 5 photos are shown. Please choose a maximum of 5.`;
      preview.append(note);
    }

    const listingForm = input.closest("[data-listing-form]");
    if (listingForm && files.length) {
      const first = files[0];
      const reader = new FileReader();
      reader.addEventListener("load", () => setPreviewImage(String(reader.result)), { once: true });
      reader.readAsDataURL(first);
    }
  };

  $$("[data-image-input]").forEach((input) => {
    input.addEventListener("change", () => renderImageFiles(input));
  });

  $$("[data-upload-zone]").forEach((zone) => {
    const input = $("[data-image-input]", zone);
    if (!input) return;
    ["dragenter", "dragover"].forEach((name) => {
      zone.addEventListener(name, (event) => {
        event.preventDefault();
        zone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      zone.addEventListener(name, (event) => {
        event.preventDefault();
        if (name === "dragleave" && zone.contains(event.relatedTarget)) return;
        zone.classList.remove("is-dragging");
      });
    });
    zone.addEventListener("drop", (event) => {
      const files = Array.from(event.dataTransfer?.files || []).filter((file) => file.type.startsWith("image/"));
      if (!files.length) return;
      try {
        const transfer = new DataTransfer();
        files.forEach((file) => transfer.items.add(file));
        input.files = transfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (_error) {
        /* Safari or older browsers may block programmatic file assignment. */
      }
    });
  });

  /* ---------------------------------------------------------------------
     Password visibility, strength and confirmation
     --------------------------------------------------------------------- */
  $$("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const wrapper = button.closest(".input-with-action") || button.parentElement;
      const input = wrapper ? $("input", wrapper) : null;
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      button.setAttribute("aria-pressed", String(show));
    });
  });

  const scorePassword = (value) => {
    if (!value) return 0;
    let score = 0;
    if (value.length >= 8) score += 1;
    if (value.length >= 12) score += 1;
    if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
    if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) score += 1;
    return Math.min(4, score);
  };

  const updatePasswordMeter = (input) => {
    const field = input.closest(".field");
    const meter = field ? $("[data-password-meter]", field) : null;
    const hint = field ? $("[data-password-hint]", field) : null;
    if (!meter) return;
    const value = input.value;
    const score = scorePassword(value);
    meter.dataset.score = String(score);
    meter.classList.toggle("is-empty", value.length === 0);
    if (!hint) return;
    if (!value) {
      hint.textContent = "Use at least 8 characters, including a letter and a number.";
      hint.classList.remove("is-strong", "is-weak");
    } else if (value.length < 8) {
      hint.textContent = "A little longer — at least 8 characters.";
      hint.classList.add("is-weak");
      hint.classList.remove("is-strong");
    } else if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
      hint.textContent = "Add a letter and a number for a stronger password.";
      hint.classList.add("is-weak");
      hint.classList.remove("is-strong");
    } else if (score >= 3) {
      hint.textContent = "Strong password. Nicely done.";
      hint.classList.add("is-strong");
      hint.classList.remove("is-weak");
    } else {
      hint.textContent = "Good start. Mix upper and lower case, numbers or symbols to strengthen it.";
      hint.classList.remove("is-weak", "is-strong");
    }
  };

  const updatePasswordMatch = (form) => {
    const password = $("[data-password-strength]", form);
    const confirm = $("[data-password-confirm]", form);
    if (!password || !confirm) return;
    const field = confirm.closest(".field");
    const note = field ? $("[data-password-match]", field) : null;
    if (!note) return;
    if (!confirm.value) {
      note.textContent = "";
      note.classList.remove("is-match", "is-mismatch");
    } else if (password.value === confirm.value) {
      note.textContent = "Passwords match.";
      note.classList.add("is-match");
      note.classList.remove("is-mismatch");
    } else {
      note.textContent = "Passwords do not match yet.";
      note.classList.add("is-mismatch");
      note.classList.remove("is-match");
    }
  };

  $$("[data-password-strength]").forEach((input) => {
    updatePasswordMeter(input);
    input.addEventListener("input", () => updatePasswordMeter(input));
  });

  $$("[data-password-strength]").forEach((input) => {
    const form = input.closest("form");
    if (form) updatePasswordMatch(form);
  });

  $$("[data-password-confirm]").forEach((input) => {
    const form = input.closest("form");
    if (form) updatePasswordMatch(form);
    input.addEventListener("input", () => {
      if (form) updatePasswordMatch(form);
    });
  });

  $$("form").forEach((form) => {
    if (!$("[data-password-confirm]", form)) return;
    form.addEventListener("submit", (event) => {
      if (event.defaultPrevented) return;
      const password = $("[data-password-strength]", form);
      const confirm = $("[data-password-confirm]", form);
      if (password && confirm && password.value !== confirm.value) {
        event.preventDefault();
        confirm.setCustomValidity("The passwords do not match.");
        confirm.reportValidity();
        confirm.addEventListener("input", () => confirm.setCustomValidity(""), { once: true });
      }
    });
  });

  /* ---------------------------------------------------------------------
     Copy-to-clipboard helpers
     --------------------------------------------------------------------- */
  const copyText = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    document.body.append(helper);
    helper.select();
    try {
      const copied = document.execCommand("copy");
      helper.remove();
      return copied;
    } catch (_error) {
      helper.remove();
      return false;
    }
  };

  $$("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const root = button.closest(".copy-field") || button.parentElement;
      const source = root ? $("[data-copy-source]", root) : null;
      if (!source) return;
      const copied = await copyText(source.value);
      const original = button.dataset.originalLabel || button.textContent.trim();
      button.dataset.originalLabel = original;
      button.classList.toggle("is-copied", copied);
      button.textContent = copied ? "Copied" : "Select and copy";
      window.setTimeout(() => {
        button.textContent = original;
        button.classList.remove("is-copied");
      }, 1800);
    });
  });

  $$("[data-copy-text]").forEach((element) => {
    element.classList.add("is-copyable");
    element.setAttribute("title", "Copy tracking code");
    element.addEventListener("click", async () => {
      const copied = await copyText(element.textContent.trim());
      if (!copied) return;
      const original = element.textContent;
      element.textContent = "Copied!";
      window.setTimeout(() => {
        element.textContent = original;
      }, 1500);
    });
  });

  /* ---------------------------------------------------------------------
     Sample-copy buttons (support reply snippets and similar helpers)
     --------------------------------------------------------------------- */
  $$("[data-fill-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = $(button.dataset.fillTarget || "");
      if (!target) return;
      target.value = button.dataset.fillText || "";
      target.focus();
      target.dispatchEvent(new Event("input", { bubbles: true }));
      button.classList.add("is-used");
      window.setTimeout(() => button.classList.remove("is-used"), 1200);
    });
  });

  /* ---------------------------------------------------------------------
     Add-listing editor: live preview, counters and conditional fields
     --------------------------------------------------------------------- */
  const listingForm = $("[data-listing-form]");
  const setPreviewImage = (source) => {
    if (!listingForm || !source) return;
    const current = $("[data-preview-image]", listingForm);
    if (!current) return;
    if (current.tagName === "IMG") {
      current.src = source;
      return;
    }
    const image = document.createElement("img");
    image.setAttribute("data-preview-image", "");
    image.alt = "Selected item preview";
    image.src = source;
    current.replaceWith(image);
  };

  if (listingForm) {
    const title = $("[data-live-title]", listingForm);
    const description = $("[data-live-description]", listingForm);
    const category = $("[data-live-category]", listingForm);
    const condition = $("[data-live-condition]", listingForm);
    const size = $("[data-live-size]", listingForm);
    const city = $("[data-live-city]", listingForm);
    const area = $("[data-live-area]", listingForm);
    const titleTarget = $("[data-preview-title]", listingForm);
    const descriptionTarget = $("[data-preview-description]", listingForm);
    const categoryTarget = $("[data-preview-category]", listingForm);
    const conditionTarget = $("[data-preview-condition]", listingForm);
    const sizeTarget = $("[data-preview-size]", listingForm);
    const locationTarget = $("[data-preview-location]", listingForm);
    const count = $("[data-character-count]", listingForm);

    const updatePreview = () => {
      if (titleTarget) titleTarget.textContent = title?.value.trim() || "Your item title";
      if (descriptionTarget) {
        descriptionTarget.textContent =
          description?.value.trim() || "A short, honest description will appear here as you type.";
      }
      if (categoryTarget) {
        const text = category && category.selectedIndex >= 0 ? category.options[category.selectedIndex].text : "";
        categoryTarget.textContent = text && category.value ? text : "Category";
      }
      if (conditionTarget) {
        conditionTarget.textContent = condition?.value || "Condition";
        conditionTarget.className = "condition condition--neutral";
      }
      if (sizeTarget) {
        const text = size && size.selectedIndex >= 0 ? size.options[size.selectedIndex].text : "";
        sizeTarget.textContent = text && size.value ? text : "Item size";
      }
      if (locationTarget) {
        const cityText = city?.value || "";
        const areaText = area?.value.trim() || "";
        locationTarget.textContent = [cityText, areaText].filter(Boolean).join(", ") || "City, area";
      }
      if (count) count.textContent = String(description?.value.length || 0);
    };

    [title, description, category, condition, size, city, area].forEach((input) => {
      if (!input) return;
      input.addEventListener("input", updatePreview);
      input.addEventListener("change", updatePreview);
    });

    $$("input[name='sample_image']", listingForm).forEach((radio) => {
      radio.addEventListener("change", () => {
        const image = radio.closest(".demo-photo")?.querySelector("img");
        if (image) setPreviewImage(image.src);
        $$(".demo-photo", listingForm).forEach((label) => {
          label.classList.toggle("is-selected", label.contains(radio) && radio.checked);
        });
      });
    });

    updatePreview();
  }

  /* ---------------------------------------------------------------------
     Conditional field toggles
     --------------------------------------------------------------------- */
  $$("[data-toggle-target]").forEach((input) => {
    const target = document.getElementById(input.dataset.toggleTarget);
    if (!target) return;
    const update = () => {
      target.hidden = !input.checked;
      target.classList.toggle("is-open", input.checked);
    };
    update();
    input.addEventListener("change", update);
  });

  /* ---------------------------------------------------------------------
     Partnered Delivery quoting
     --------------------------------------------------------------------- */
  $$("[data-delivery-form]").forEach((form) => {
    const methodInputs = $$("[data-method-option]", form);
    const pickupFields = $("[data-pickup-fields]", form);
    const deliveryFields = $("[data-delivery-fields]", form);
    const deliveryAddress = $("[data-delivery-address]", form);
    const quoteUrl = form.dataset.quoteUrl;
    const listingId = form.dataset.listingId;
    const quoteBox = $("[data-quote-box]", form);
    const message = $("[data-quote-message]", form);
    let controller = null;

    const updateRequirements = () => {
      const selected = form.querySelector("input[name='receive_method']:checked");
      const isDelivery = selected?.value === "delivery";
      if (pickupFields) pickupFields.hidden = isDelivery;
      if (deliveryFields) deliveryFields.hidden = !isDelivery;
      if (deliveryAddress) deliveryAddress.required = isDelivery;
    };

    const setQuoteValue = (selector, value) => {
      const target = $(selector, form);
      if (target) target.textContent = value;
    };

    const loadQuote = async () => {
      if (!quoteUrl || !listingId) return;
      if (form.querySelector("input[name='receive_method']:checked")?.value !== "delivery") return;
      if (controller) controller.abort();
      controller = new AbortController();
      quoteBox?.classList.add("is-loading");
      if (message) message.textContent = "Preparing your inclusive delivery estimate…";

      const params = new URLSearchParams({ listing_id: listingId });
      try {
        const response = await fetch(`${quoteUrl}?${params.toString()}`, {
          headers: { Accept: "application/json" },
          signal: controller.signal,
          credentials: "same-origin",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
          throw new Error(data.message || "A quote could not be prepared right now.");
        }
        setQuoteValue("[data-quote-distance]", `${data.distance_km} km`);
        setQuoteValue("[data-quote-fee]", data.fee_display);
        setQuoteValue("[data-quote-partner]", data.partner_name);
        setQuoteValue("[data-quote-eta]", data.eta);
        if (message) message.textContent = data.message;
        quoteBox?.classList.add("is-ready");
      } catch (error) {
        if (error.name === "AbortError") return;
        if (message) message.textContent = error.message || "A quote could not be prepared right now.";
        quoteBox?.classList.remove("is-ready");
      } finally {
        quoteBox?.classList.remove("is-loading");
      }
    };

    methodInputs.forEach((input) => {
      input.addEventListener("change", () => {
        updateRequirements();
        if (input.value === "delivery" && input.checked) loadQuote();
      });
    });
    updateRequirements();
    if (form.querySelector("input[name='receive_method']:checked")?.value === "delivery") loadQuote();
  });

  /* ---------------------------------------------------------------------
     Messages: conversation search, chat scroll, composer and attachments
     --------------------------------------------------------------------- */
  const conversationSearch = $("[data-conversation-search]");
  if (conversationSearch) {
    const items = $$("[data-conversation-item]");
    const noResults = $("[data-conversation-no-results]");
    const filter = () => {
      const needle = conversationSearch.value.trim().toLowerCase();
      let visible = 0;
      items.forEach((item) => {
        const matches = !needle || item.textContent.toLowerCase().includes(needle);
        item.hidden = !matches;
        if (matches) visible += 1;
      });
      if (noResults) noResults.hidden = !needle || visible > 0;
    };
    conversationSearch.addEventListener("input", filter);
    filter();
  }

  const chatThread = $("[data-chat-thread]");
  const scrollThreadToEnd = () => {
    if (chatThread) chatThread.scrollTop = chatThread.scrollHeight;
  };
  if (chatThread) {
    scrollThreadToEnd();
    requestAnimationFrame(scrollThreadToEnd);
    window.addEventListener("load", scrollThreadToEnd, { once: true });
    window.addEventListener("pageshow", scrollThreadToEnd);
  }

  $$("[data-chat-input]").forEach((input) => {
    const form = input.closest("form");
    const grow = () => {
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 128)}px`;
    };
    grow();
    input.addEventListener("input", grow);
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
      if (!input.value.trim() || !form) return;
      event.preventDefault();
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    });
  });

  $$("[data-file-input]").forEach((input) => {
    const form = input.closest("form");
    const note = form ? $("[data-file-note]", form) : null;
    const resetNote = () => {
      if (note) note.textContent = "Photos help confirm condition.";
    };
    input.addEventListener("change", () => {
      if (!note) return;
      const file = (input.files || [])[0];
      note.textContent = file ? `Ready to send: ${file.name}` : "Photos help confirm condition.";
    });
    if (form) form.addEventListener("reset", resetNote);
  });


  /* ---------------------------------------------------------------------
     Boost checkout summary
     --------------------------------------------------------------------- */
  $$("[data-boost-form]").forEach((form) => {
    const options = $$("[data-package-option]", form);
    const nameTarget = $("[data-checkout-name]", form);
    const daysTarget = $("[data-checkout-days]", form);
    const priceTarget = $("[data-checkout-price]", form);

    const update = () => {
      const selected = form.querySelector("[data-package-option]:checked") || options[0];
      if (!selected) return;
      const price = Number(selected.dataset.packagePrice || 0);
      const days = Number(selected.dataset.packageDays || 0);
      if (nameTarget) nameTarget.textContent = selected.dataset.packageName || "Standard";
      if (daysTarget) daysTarget.textContent = days > 0 ? `${days} days` : "No expiry";
      if (priceTarget) priceTarget.textContent = price > 0 ? money(price) : "₱0";
    };

    options.forEach((option) => option.addEventListener("change", update));
    update();
  });

  /* ---------------------------------------------------------------------
     Admin content: category placement selector
     --------------------------------------------------------------------- */
  $$("[data-ad-placement]").forEach((select) => {
    const form = select.closest("form");
    const category = form ? $("select[name='category_id']", form) : null;
    if (!category) return;
    const update = () => {
      const isCategory = select.value === "category";
      category.disabled = !isCategory;
      category.required = isCategory;
      category.closest(".field")?.classList.toggle("is-muted", !isCategory);
    };
    select.addEventListener("change", update);
    update();
  });

  /* ---------------------------------------------------------------------
     Action menus, reveal animations and small finishing touches
     --------------------------------------------------------------------- */
  $$("details.action-menu").forEach((menuElement) => {
    menuElement.addEventListener("toggle", () => {
      if (!menuElement.open) return;
      $$("details.action-menu").forEach((other) => {
        if (other !== menuElement) other.open = false;
      });
    });
  });
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest("details.action-menu")) return;
    $$("details.action-menu[open]").forEach((menuElement) => {
      menuElement.open = false;
    });
  });

  // Keep the active workspace item visible when the dashboard rail becomes horizontal.
  const scrollActiveDashboardNav = () => {
    const rail = $(".dash-sidebar");
    const active = $(".dash-nav-link.is-active", rail || document);
    if (!rail || !active || rail.scrollWidth <= rail.clientWidth + 1) return;
    const railRect = rail.getBoundingClientRect();
    const activeRect = active.getBoundingClientRect();
    const target = rail.scrollLeft + (activeRect.left - railRect.left) - 10;
    rail.scrollLeft = Math.max(0, target);
  };
  scrollActiveDashboardNav();
  window.addEventListener("load", scrollActiveDashboardNav, { once: true });
  window.addEventListener("resize", scrollActiveDashboardNav, { passive: true });

  // Make wide data tables discoverable on touch screens.
  const tableHints = [];
  $$(".table-wrap").forEach((wrap) => {
    const hint = document.createElement("p");
    hint.className = "table-scroll-hint";
    hint.textContent = "Swipe or scroll to see the full table →";
    wrap.before(hint);
    const update = () => {
      hint.hidden = wrap.scrollWidth <= wrap.clientWidth + 2;
    };
    tableHints.push(update);
    update();
    if ("ResizeObserver" in window) {
      new ResizeObserver(update).observe(wrap);
    }
  });
  window.addEventListener(
    "resize",
    () => tableHints.forEach((update) => update()),
    { passive: true }
  );

  const revealItems = $$(".reveal");
  if ("IntersectionObserver" in window && revealItems.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );
    revealItems.forEach((item) => observer.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  }

  // Smoothly close the mobile menu after choosing an in-page link.
  $$(".mobile-nav a, .mobile-menu-actions a").forEach((link) => {
    link.addEventListener("click", () => setMenu(false, false));
  });
})();

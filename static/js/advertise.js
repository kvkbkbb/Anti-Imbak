/* Advertising page — package selection jumps to the enquiry form. */
(() => {
  "use strict";

  const form = document.querySelector(".advertise-form");
  const packageSelect = form ? form.querySelector("select[name='package_id']") : null;

  document.querySelectorAll("[data-package-jump]").forEach((link) => {
    link.addEventListener("click", () => {
      if (!packageSelect) return;
      const value = link.dataset.packageJump;
      if (!value) return;
      packageSelect.value = value;
      packageSelect.classList.add("is-highlighted");
      window.setTimeout(() => packageSelect.classList.remove("is-highlighted"), 2200);
      window.setTimeout(() => packageSelect.focus({ preventScroll: true }), 450);
    });
  });

  if (form) {
    form.addEventListener("submit", (event) => {
      if (!form.checkValidity()) {
        event.preventDefault();
        form.reportValidity();
      }
    });
  }
})();

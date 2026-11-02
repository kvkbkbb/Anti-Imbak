(function () {
  "use strict";

  var toast;

  function showNotice(message) {
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "static-preview-toast";
      toast.setAttribute("role", "status");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(showNotice.timer);
    showNotice.timer = window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 4200);
  }

  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (form.closest(".static-preview-bar")) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      showNotice(
        "This is a read-only GitHub Pages preview. Sign-in, search filters and " +
          "donation actions work in the Flask app. See the README to run it locally."
      );
    },
    true
  );

  document.addEventListener(
    "click",
    function (event) {
      var link = event.target.closest("a[data-preview-missing]");
      if (!link) return;
      event.preventDefault();
      showNotice(
        "That page belongs to the signed-in workspace or a live action. " +
          "Run the Flask app locally to explore it."
      );
    },
    true
  );
})();

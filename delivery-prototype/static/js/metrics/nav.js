(function () {
  "use strict";

  document.querySelectorAll(".field-nav:not(.field-nav-prototype) a").forEach(function (link) {
    if (link.pathname === window.location.pathname) {
      link.classList.add("active");
    }
  });
})();

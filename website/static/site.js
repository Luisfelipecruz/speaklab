// Three things, and the site reads the same without any of them: it marks that scripts run,
// so the narrow-screen menu can collapse; it opens and closes that menu; and it draws a
// Mermaid diagram when one comes near the viewport. Mermaid's script is 1.5 MB compressed,
// so it is fetched only on a page that has a diagram, only as the diagram is about to be
// seen, pinned to one release and checked against that release's hash. Until it has
// drawn, the diagram's source shows.
(function () {
  "use strict";

  var MERMAID = {
    src: "https://cdn.jsdelivr.net/npm/mermaid@12.0.0/dist/mermaid.min.js",
    integrity: "sha384-xzghz1GQ5u9HCpVskeDPqMsdogD1yvuMQbEK53+wi+G70+6J1AG0L2cfi9PHjDWI",
  };

  document.documentElement.classList.add("js");

  var menu = document.querySelector(".menu");
  var sidebar = document.getElementById("sidebar");
  if (menu && sidebar) {
    var setOpen = function (open) {
      menu.setAttribute("aria-expanded", String(open));
      sidebar.toggleAttribute("data-open", open);
    };
    menu.addEventListener("click", function () {
      setOpen(menu.getAttribute("aria-expanded") !== "true");
    });
    sidebar.addEventListener("click", function (event) {
      if (event.target.closest("a")) setOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && sidebar.hasAttribute("data-open")) {
        setOpen(false);
        menu.focus();
      }
    });
  }

  var diagrams = Array.prototype.slice.call(document.querySelectorAll("pre.mermaid"));
  if (!diagrams.length) return;

  var started = false;
  function draw() {
    if (started) return;
    started = true;
    var script = document.createElement("script");
    script.src = MERMAID.src;
    script.integrity = MERMAID.integrity;
    script.crossOrigin = "anonymous";
    script.onload = function () {
      var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      window.mermaid.initialize({
        startOnLoad: false,
        securityLevel: "antiscript",
        theme: dark ? "dark" : "default",
      });
      window.mermaid.run({ nodes: diagrams }).then(function () {
        diagrams.forEach(function (node) {
          node.classList.add("drawn");
        });
      });
    };
    document.head.appendChild(script);
  }

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(
      function (entries) {
        if (entries.some(function (entry) { return entry.isIntersecting; })) {
          observer.disconnect();
          draw();
        }
      },
      { rootMargin: "600px 0px" }
    );
    diagrams.forEach(function (node) {
      observer.observe(node);
    });
  } else {
    draw();
  }
})();

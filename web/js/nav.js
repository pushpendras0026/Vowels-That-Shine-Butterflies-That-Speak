// Shared navigation. Every page: <link rel="stylesheet" href="css/site.css"> + <nav id="site-nav"></nav>
// + <script type="module" src="js/nav.js"></script>
export const PAGES = [
  ["index.html", "Story"],
  ["theory.html", "Theory"],
  ["lab.html", "Live Voice Lab"],
  ["garden.html", "Butterfly Garden"],
  ["results.html", "Results"],
  ["experiments.html", "Experiments"],
  ["record.html", "Record your voice"],
  ["video.html", "Video"],
  ["tests.html", "JS ⇄ Python tests"],
];

function render() {
  const nav = document.getElementById("site-nav");
  if (!nav) return;
  const here = location.pathname.split("/").pop() || "index.html";
  nav.innerHTML = `<a class="brand" href="index.html">Vowels That Shine, <span>Butterflies That Speak</span></a>` +
    PAGES.map(([href, name]) => `<a class="tab${href === here ? " active" : ""}" href="${href}">${name}</a>`).join("");
}
render();

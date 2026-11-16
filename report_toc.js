// Derive navigation from rendered Markdown, including Setext and inline headings.
// Scroll without changing the hash, which belongs to trame-router.
(function () {
  let content = null;
  let toc = null;
  let headings = [];
  let labels = [];
  let pending = false;

  function refresh() {
    pending = false;
    const nextContent = document.querySelector('.report-content');
    const nextToc = document.querySelector('.report-toc');
    if (!nextContent || !nextToc) {
      content = toc = null;
      headings = [];
      labels = [];
      return;
    }
    const nextHeadings = Array.from(nextContent.querySelectorAll('h1,h2,h3,h4,h5,h6'));
    const nextLabels = nextHeadings.map(h => {
      const label = h.cloneNode(true);
      label.querySelectorAll('.header-anchor').forEach(anchor => anchor.remove());
      return label.textContent.trim();
    });
    if (content === nextContent && toc === nextToc &&
        headings.length === nextHeadings.length &&
        nextHeadings.every((h, i) => h === headings[i] && nextLabels[i] === labels[i])) {
      return;
    }
    content = nextContent;
    toc = nextToc;
    headings = nextHeadings;
    labels = nextLabels;
    toc.hidden = headings.length === 0;
    const items = toc.querySelector('.report-toc__items');
    items.replaceChildren();
    const baseLevel = Math.min(...headings.map(h => Number(h.tagName.slice(1))));
    headings.forEach((heading, index) => {
      const item = document.createElement('li');
      item.style.setProperty('--toc-level', Number(heading.tagName.slice(1)) - baseLevel);
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = labels[index] || 'Untitled section';
      button.addEventListener('click', () => {
        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        heading.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      });
      item.appendChild(button);
      items.appendChild(item);
    });
  }

  function start() {
    // Markdown renders asynchronously; also rebuild when routes replace a report.
    new MutationObserver(() => {
      if (!pending) {
        pending = true;
        window.requestAnimationFrame(refresh);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
    refresh();
  }
  if (document.body) start();
  else document.addEventListener('DOMContentLoaded', start, { once: true });
})();

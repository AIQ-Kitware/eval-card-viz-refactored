"""App shell — layout root, top bar, view routing, and toast.

Mirrors the mockup's ``app.jsx``: a sticky top bar with brand + live
verdict counts, a body that switches between the list view and a
full-page detail view, and a toast for upload feedback.
"""

from pathlib import Path

from trame.ui.vuetify3 import VAppLayout
from trame.widgets import client, html
from trame.widgets import vuetify3 as v3

from ui_list import build_list_view
from ui_detail import build_detail_view

STYLE_PATH = Path(__file__).parent / "styles.css"

# Copy-to-clipboard buttons carry their text in a `data-copy-text` attribute
# (bound reactively via Vue, see tag_chips()'s data-group for the same
# pattern) rather than a `click=` handler — Vue's runtime template compiler
# evaluates `click=` expressions inside a `with (_ctx) { ... }` block that
# intercepts bare identifiers, so browser globals like `setTimeout` or
# `navigator` silently resolve to `undefined` there instead of the real
# thing. A single delegated listener on the real document, registered once
# outside any Vue expression, sidesteps that entirely — and needs no global
# function name, unlike a `window.foo` callback invoked from `click=`.
COPY_SCRIPT = """
(function () {
  function fallbackCopy(value) {
    var ta = document.createElement('textarea');
    ta.value = value;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
    } catch (err) {
      console.error('MAGNET: clipboard copy failed', err);
    }
    document.body.removeChild(ta);
  }

  function flashCopied(button) {
    var label = button.querySelector('.copybtn__label');
    if (!label) return;
    var original = label.textContent;
    button.classList.add('copybtn--copied');
    label.textContent = 'Copied';
    setTimeout(function () {
      button.classList.remove('copybtn--copied');
      label.textContent = original;
    }, 1500);
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-copy-text]');
    if (!button) return;
    var text = button.getAttribute('data-copy-text') || '';
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(
        function () { flashCopied(button); },
        function () { fallbackCopy(text); flashCopied(button); }
      );
    } else {
      fallbackCopy(text);
      flashCopied(button);
    }
  });
})();
"""


def build_layout(app):
    """Construct the full UI for an EvaluationCardsApp instance."""
    with VAppLayout(app.server) as layout:
        client.Style(STYLE_PATH.read_text())
        client.Script(COPY_SCRIPT)

        with html.Div(classes="app app--noqueue"):
            _top_bar(app)
            with html.Div(classes="app__body"):
                # List view (library)
                with html.Div(v_if="view === 'list'", style="min-width: 0;"):
                    build_list_view(app)
                # Detail view (single card)
                with html.Div(v_if="view === 'detail' && selected_card", style="min-width: 0;"):
                    build_detail_view(app)

        # Upload feedback toast
        with html.Div(
            v_if="upload_show",
            classes=(
                "'toast' + (upload_color === 'warning' ? ' toast--warning' : "
                "upload_color === 'error' ? ' toast--error' : '')",
            ),
        ):
            html.Span("{{ upload_msg }}")
            html.Button("✕", classes="toast__close", click="upload_show = false")

    return layout


def _top_bar(app):
    with html.Header(classes="topbar"):
        # Brand
        with html.Div(classes="topbar__brand"):
            html.Img(src=("brand_mark_src",), classes="brand-mark")
            with html.Div(classes="brand-text"):
                html.Div("MAGNET", classes="brand-name")
                html.Div("Evaluation Cards", classes="brand-sub")

        # Nav (single section for now; placeholder for future areas)
        with html.Nav(classes="topbar__nav"):
            html.A("Evaluations", classes="navlink navlink--active", click="view = 'list'")

        # Right: verdict counts + local upload
        with html.Div(classes="topbar__right"):
            # with html.Div(classes="status"):
            #     html.Span(classes="dot dot--ok")
            #     html.Span("{{ n_verified_total }} verified")
            #     html.Span("·", classes="status__sep")
            #     html.Span(classes=("'dot ' + (n_falsified_total > 0 ? 'dot--run' : 'dot--muted')",))
            #     html.Span("{{ n_falsified_total }} falsified")
            with html.Div(
                title=(
                    "Zip a directory containing one or more run folders "
                    "(each with results/, card.yaml, and verdict.json)."
                ),
            ):
                v3.VFileInput(
                    v_if="is_local_deployment",
                    v_model=("uploaded_file", None),
                    accept=".zip",
                    label="Upload local run (.zip)",
                    prepend_icon="",
                    prepend_inner_icon="mdi-upload",
                    variant="underlined",
                    density="compact",
                    hide_details=True,
                    flat=True,
                    style="min-width: 260px;",
                )

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


def build_layout(app):
    """Construct the full UI for an EvaluationCardsApp instance."""
    with VAppLayout(app.server) as layout:
        client.Style(STYLE_PATH.read_text())

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
            with html.Div(classes="status"):
                html.Span(classes="dot dot--ok")
                html.Span("{{ n_verified_total }} verified")
                html.Span("·", classes="status__sep")
                html.Span(classes=("'dot ' + (n_falsified_total > 0 ? 'dot--run' : 'dot--muted')",))
                html.Span("{{ n_falsified_total }} falsified")
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

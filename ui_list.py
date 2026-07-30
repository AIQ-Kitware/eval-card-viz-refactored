"""Library (list) view — hero, search toolbar, filter sidebar, card grid/rows.

Mirrors the mockup's ``components.jsx``: a checkbox filter sidebar with
per-value counts, active-filter chips, a grid/list layout toggle, and
evaluation cards that carry a status pill, tag chips, headline metrics,
and a pass-rate sparkline.

SVG note: trame's html widgets don't expose SVG child elements, so small
static icons are inlined as raw markup (widget string children are placed
verbatim in the Vue template) and data-driven graphics (sparklines, the
overview chart) are precomputed server-side and bound with ``v-html``.
"""

from trame.widgets import html

# -------- Icons (inline SVG, kept tiny and consistent with the mockup) --------
_S = 'fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"'

ICONS = {
    "search": f'<svg viewBox="0 0 16 16" width="14" height="14" {_S}><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 L14 14"/></svg>',
    "grid": f'<svg viewBox="0 0 16 16" width="14" height="14" {_S}><rect x="1.5" y="1.5" width="5" height="5"/><rect x="9.5" y="1.5" width="5" height="5"/><rect x="1.5" y="9.5" width="5" height="5"/><rect x="9.5" y="9.5" width="5" height="5"/></svg>',
    "list": f'<svg viewBox="0 0 16 16" width="14" height="14" {_S}><path d="M2 4h12M2 8h12M2 12h12"/></svg>',
    "arrowLeft": f'<svg viewBox="0 0 16 16" width="14" height="14" {_S}><path d="M10 3 L4 8 L10 13"/></svg>',
    "chevron": f'<svg viewBox="0 0 16 16" width="12" height="12" {_S}><path d="M6 3 L11 8 L6 13"/></svg>',
    "x": f'<svg viewBox="0 0 16 16" width="12" height="12" {_S}><path d="M4 4 L12 12 M12 4 L4 12"/></svg>',
}


def icon(name):
    html.Span(ICONS[name], style="display: inline-flex;")


def status_pill(expr):
    """Verdict pill for a card object ``expr`` exposing ``.result`` of
    VERIFIED / FALSIFIED (anything else renders muted)."""
    html.Span(
        "{{ %s.result === 'VERIFIED' ? 'Verified' : %s.result === 'FALSIFIED' ? 'Falsified' : %s.result }}"
        % (expr, expr, expr),
        classes=(
            f"'pill ' + ({expr}.result === 'VERIFIED' ? 'pill--ok' : "
            f"{expr}.result === 'FALSIFIED' ? 'pill--bad' : 'pill--muted')",
        ),
    )


def tag_chips(list_expr, on_click=None):
    """Row of tag chips from a precomputed ``[{label, group}]`` list."""
    with html.Template(v_for=f"t in {list_expr}", key=("t.group + t.label",)):
        kwargs = {"classes": "tag"}
        if on_click:
            kwargs["click"] = (on_click, "[t.group, t.label]")
            kwargs["classes"] = "tag tag--btn"
        html.Span(
            "{{ t.label }}",
            __properties=[("data_group", ":data-group")],
            data_group="t.group",
            **kwargs,
        )


def build_list_view(app):
    with html.Div(classes="list"):
        # Hero
        with html.Div(classes="list__hero"):
            html.H1("Evaluation Cards", classes="list__h1")
            html.P(
                "<TODO: Get the right description for the evaluation",
                classes="list__lede",
            )

        # Toolbar: search + layout toggle
        with html.Div(classes="list__toolbar"):
            with html.Div(classes="search"):
                icon("search")
                html.Input(
                    type="text",
                    placeholder="Search cards by title, description, or algorithm…",
                    v_model=("search_term",),
                )
                with html.Button(v_if="search_term", classes="search__clear", click="search_term = ''"):
                    icon("x")
            with html.Div(classes="list__layout"):
                html.Span("{{ filtered_cards.length }} of {{ cards.length }}", classes="muted-tiny")
                with html.Div(classes="seg"):
                    with html.Button(
                        classes=("'seg__btn' + (layout_mode === 'grid' ? ' seg__btn--active' : '')",),
                        click="layout_mode = 'grid'",
                    ):
                        icon("grid")
                        html.Span("Grid")
                    with html.Button(
                        classes=("'seg__btn' + (layout_mode === 'list' ? ' seg__btn--active' : '')",),
                        click="layout_mode = 'list'",
                    ):
                        icon("list")
                        html.Span("List")

        # Split: filter sidebar + results
        with html.Div(classes="list__split"):
            _filter_panel(app)
            with html.Div(classes="list__main"):
                _active_chips(app)
                # Empty state
                with html.Div(
                    v_if="filtered_cards.length === 0",
                    classes="empty-state empty-state--center",
                ):
                    html.Div("No evaluation cards match.", classes="empty-state__title")
                    html.Div("Try removing a filter or clearing your search.", classes="empty-state__sub")
                # Grid mode
                with html.Div(v_else_if="layout_mode === 'grid'", classes="grid"):
                    with html.Template(v_for="c in filtered_cards", key=("c.id",)):
                        _card(app)
                # List mode
                with html.Div(v_else=True, classes="rows"):
                    with html.Template(v_for="c in filtered_cards", key=("c.id",)):
                        _row(app)


def _filter_panel(app):
    with html.Aside(classes="filters"):
        with html.Div(classes="filters__head"):
            html.Span("Filters", classes="filters__title")
            html.Button(
                "Clear all",
                v_if="active_chips.length > 0",
                classes="link-btn",
                click=app.clear_filters,
            )
        with html.Template(v_for="g in filter_groups", key=("g.key",)):
            with html.Div(classes="filters__group"):
                html.Div("{{ g.label }}", classes="filters__label")
                with html.Div(classes="filters__values"):
                    with html.Template(v_for="v in g.values", key=("v",)):
                        with html.Div(
                            classes=(
                                "'filter-row' + (selected_filters[g.key].includes(v) ? ' filter-row--active' : '')",
                            ),
                            click=(app.toggle_filter, "[g.key, v]"),
                        ):
                            html.Input(
                                type="checkbox",
                                checked=("selected_filters[g.key].includes(v)",),
                                style="pointer-events: none;",
                            )
                            html.Span("{{ v }}", classes="filter-row__label")
                            html.Span(
                                "{{ filter_counts[g.key][v] || 0 }}",
                                classes="filter-row__count",
                            )


def _active_chips(app):
    with html.Div(v_if="active_chips.length > 0", classes="active-chips"):
        html.Span("Filters:", classes="muted-tiny")
        with html.Template(v_for="chip in active_chips", key=("chip.key + chip.value",)):
            with html.Span(
                classes="chip-active",
                click=(app.toggle_filter, "[chip.key, chip.value]"),
            ):
                html.Span("{{ chip.value }}")
                icon("x")
        html.Button("Clear", classes="link-btn", click=app.clear_filters)


def _card(app):
    """Grid-mode evaluation card."""
    with html.Button(classes="card", click=(app.select_card, "[c.id]")):
        with html.Div(classes="card__head"):
            with html.Div(classes="card__title-row"):
                html.Span("{{ c.short }}", classes="card__short")
                status_pill("c")
            html.H3("{{ c.card.title }}", classes="card__title")
            html.P("{{ c.summary }}", classes="card__summary")
        with html.Div(classes="card__tags"):
            tag_chips("c.tag_list.slice(0, 5)")
        with html.Div(classes="card__foot"):
            with html.Div(classes="card__foot-inner"):
                with html.Div(classes="metric"):
                    html.Span("Pass", classes="metric__label")
                    html.Span("{{ c.pass_rate }}%", classes="metric__value")
                with html.Div(classes="metric"):
                    html.Span("Sweeps", classes="metric__label")
                    html.Span("{{ c.n_runs }}", classes="metric__value")
                html.Div(v_html=("c.spark_svg",), classes="card__spark")


def _row(app):
    """List-mode evaluation row."""
    with html.Button(classes="row", click=(app.select_card, "[c.id]")):
        with html.Div(classes="row__main"):
            with html.Div(classes="row__title-line"):
                html.Span("{{ c.short }}", classes="row__short")
                html.Span("{{ c.card.title }}", classes="row__title")
                status_pill("c")
            html.P("{{ c.summary }}", classes="row__summary")
        with html.Div(classes="row__tags"):
            tag_chips("c.tag_list.slice(0, 3)")
        with html.Div(classes="row__metric"):
            html.Span("Pass", classes="metric__label")
            html.Span("{{ c.pass_rate }}%", classes="metric__value")
        with html.Div(classes="row__metric"):
            html.Span("Sweeps", classes="metric__label")
            html.Span("{{ c.n_runs }}", classes="metric__value")
        html.Div(v_html=("c.spark_svg",), classes="row__spark")
        with html.Div(classes="row__arrow"):
            icon("chevron")

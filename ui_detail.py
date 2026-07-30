"""Detail view — header, tabs, overview metrics + chart, sweep runs.

Mirrors the mockup's ``detail.jsx``: a back link, a header with the card
short code / title / summary / status, a tag list, an underlined tab
strip, metric blocks with a pass-rate chart on the Overview tab — mapped
onto real MAGNET artifacts (claim, sweep verdicts, symbols, card YAML,
figures, execution log).
"""

from trame.widgets import html
from trame.widgets import markdown

from ui_list import icon, status_pill, tag_chips

TABS = [
    ("overview", "Overview"),
    ("runs", "Sweep runs"),
    ("card", "Card"),
    ("figures", "Figures"),
    ("log", "Log"),
]


def build_detail_view(app):
    with html.Div(classes="detail"):
        _header(app)

        # Tab strip
        with html.Div(classes="tabs"):
            for key, label in TABS:
                kwargs = {}
                if key == "figures":
                    kwargs["v_if"] = "selected_card.figures && selected_card.figures.length > 0"
                html.Button(
                    label,
                    classes=(f"'tab' + (current_tab === '{key}' ? ' tab--active' : '')",),
                    click=f"current_tab = '{key}'",
                    **kwargs,
                )

        with html.Div(classes="detail__body"):
            with html.Div(v_if="current_tab === 'overview'"):
                _overview()
            with html.Div(v_if="current_tab === 'runs'"):
                _sweep_runs(app)
            with html.Div(v_if="current_tab === 'card'"):
                html.Pre("{{ selected_card.card_yaml }}", classes="codeblock")
            with html.Div(v_if="current_tab === 'figures'"):
                _figures()
            with html.Div(v_if="current_tab === 'log'"):
                html.Pre("{{ selected_card.log }}", classes="logblock")


def _header(app):
    with html.Div(classes="detail__header"):
        with html.Button(classes="back", click="view = 'list'"):
            icon("arrowLeft")
            html.Span("All evaluation cards")

        with html.Div(classes="detail__title-row"):
            with html.Div():
                html.Div(
                    "{{ selected_card.short }} · {{ selected_card.organization }}",
                    classes="detail__short",
                )
                html.H1("{{ selected_card.card.title }}", classes="detail__title")
                html.P("{{ selected_card.summary }}", classes="detail__summary")
            with html.Div(classes="detail__title-meta"):
                status_pill("selected_card")
                html.Div(
                    "Last sweep · {{ selected_card.last_run }}",
                    v_if="selected_card.last_run",
                    classes="muted-tiny",
                )
                html.Div(
                    "{{ selected_card.submitter }}",
                    v_if="selected_card.submitter",
                    classes="muted-tiny",
                )

        with html.Div(classes="detail__taglist"):
            tag_chips("selected_card.tag_list", on_click=app.add_filter)

        # External links from the card definition
        with html.Div(v_if="selected_card.links.length > 0", classes="linkrow"):
            with html.Template(v_for="l in selected_card.links", key=("l.url",)):
                with html.A(classes="linkchip", href=("l.url",), target="_blank", rel="noopener"):
                    html.Span("{{ l.kind }}", classes="linkchip__kind")
                    html.Span("{{ l.title }}")


def _metric_block(label, value_expr, sub):
    with html.Div(classes="mblock"):
        html.Div(label, classes="mblock__label")
        html.Div("{{ %s }}" % value_expr, classes="mblock__value")
        html.Div(sub, classes="mblock__sub")


def _overview():
    with html.Div(classes="overview"):
        # Headline metrics
        with html.Div(classes="overview__metrics"):
            _metric_block("Pass rate", "selected_card.pass_rate + '%'", "verified sweeps")
            _metric_block("Verified", "selected_card.n_verified", "assertion holds")
            _metric_block("Falsified", "selected_card.n_falsified", "assertion fails")
            _metric_block("Sweeps", "selected_card.n_runs", "parameter sets")
            _metric_block("Version", "selected_card.version", "card definition")

        # Cumulative pass-rate chart over the sweep sequence (server-rendered SVG)
        with html.Div(classes="overview__chart"):
            with html.Div(classes="chart-head"):
                html.Div("Cumulative pass rate — sweep sequence", classes="chart-title")
                html.Span("y = fraction verified", classes="muted-tiny")
            html.Div(v_html=("selected_card.chart_svg",))

        # Claim block with description / python toggle
        with html.Div(classes="claim"):
            with html.Div(classes="claim__head"):
                html.Div("Claim", classes="claim__title")
                with html.Div(classes="tabs tabs--pill", style="border-bottom: none; margin-bottom: 0;"):
                    html.Button(
                        "Description",
                        classes=("'tab' + (show_python_claim ? '' : ' tab--active')",),
                        click="show_python_claim = false",
                    )
                    html.Button(
                        "Python",
                        classes=("'tab' + (show_python_claim ? ' tab--active' : '')",),
                        click="show_python_claim = true",
                    )
            with html.Div(v_if="!show_python_claim", classes="claim__desc"):
                markdown.Markdown(content=("selected_card.card.description",))
            with html.Div(v_else=True):
                html.Pre("{{ selected_card.claim }}", classes="codeblock codeblock--inline")
            with html.Div(classes="claim__agg muted-tiny"):
                html.Span("Aggregation · {{ selected_card.agg_label }}")


def _sweep_runs(app):
    with html.Div(classes="sweeps"):
        # Verdict tally + aggregation strategy banner
        with html.Div(classes="sweeps__banner"):
            html.Span(classes="dot dot--ok")
            html.Span("{{ selected_card.n_verified }} verified")
            html.Span("·", classes="status__sep")
            html.Span(classes=("'dot ' + (selected_card.n_falsified > 0 ? 'dot--run' : 'dot--muted')",))
            html.Span("{{ selected_card.n_falsified }} falsified")
            html.Span("·", classes="status__sep")
            html.Span("{{ selected_card.agg_label }}")

        with html.Template(v_for="run in selected_card.runs", key=("run.id",)):
            with html.Div(classes=("'sweep' + (run.ok ? '' : ' sweep--bad')",)):
                with html.Div(classes="sweep__top"):
                    html.Span("sweep {{ run.id }}", classes="sweep__id")
                    with html.Div(style="display: flex; align-items: center; gap: 10px;"):
                        html.Span("{{ run.time_str }}", classes="sweep__time")
                        html.Span(
                            "{{ run.status }}",
                            classes=("'pill ' + (run.ok ? 'pill--ok' : 'pill--bad')",),
                        )
                # Assertion output shown only when the claim failed
                html.Pre("{{ run.output }}", v_if="!run.ok && run.output", classes="sweep__output")
                # Symbols toggle + table
                with html.Button(classes="sweep__toggle", click=(app.toggle_symbols, "[run.id]")):
                    icon("chevron")
                    html.Span(
                        "{{ expanded_symbols_runs.includes(run.id) ? 'Hide symbols' : 'Symbols (' + run.symbols_rows.length + ')' }}"
                    )
                with html.Div(v_if="expanded_symbols_runs.includes(run.id)", classes="sweep__symbols"):
                    with html.Table(classes="rtable rtable--dense"):
                        with html.Thead():
                            with html.Tr():
                                html.Th("Symbol")
                                html.Th("Value")
                        with html.Tbody():
                            with html.Template(v_for="s in run.symbols_rows", key=("s.name",)):
                                with html.Tr():
                                    html.Td("{{ s.name }}", classes="mono")
                                    html.Td("{{ s.value }}", classes="mono prompt-cell", title=("s.value",))


def _figures():
    with html.Div(classes="figures"):
        with html.Template(v_for="(f, i) in selected_card.figures", key=("i",)):
            with html.Div(classes="figure"):
                html.Img(src=("f",))

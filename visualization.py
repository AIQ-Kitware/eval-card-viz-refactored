"""MAGNET evaluation card dashboard (trame).

Data layer + application state. The UI lives in ``ui_shell`` /
``ui_list`` / ``ui_detail`` (mirroring the reference mockup's
``app.jsx`` / ``components.jsx`` / ``detail.jsx``) and is styled by
``styles.css``.
"""

import argparse
import base64
import io
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime

import ubelt as ub
import yaml
from trame.app import get_server
from trame.decorators import TrameApp, change

from ui_shell import build_layout

FAVICON_PATH = ub.Path(__file__).parent / "assets" / "MAGNET_icon.png"

# ---------------------------------------------------------------------------
# Card enrichment — derived fields consumed by the UI templates
# ---------------------------------------------------------------------------

SPARK_W, SPARK_H = 88, 24
CHART_W, CHART_H, CHART_P = 720, 220, 32

FILTER_GROUPS = [
    {"key": "milestone", "label": "Milestone"},
    {"key": "organization", "label": "Organization"},
    {"key": "result", "label": "Result"},
    {"key": "tags", "label": "Tags"},
]

DEFAULT_FILTERS = {"milestone": ["PhaseI_DryRun"]}


def make_short(name):
    """Compact mono code for a card, e.g. 'DKPS_PerInstance' -> 'DPI'."""
    words = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]*|[a-z]+|\d+", name.replace("_", " "))
    if not words:
        return name[:6].upper()
    if len(words) == 1:
        return words[0][:8].upper()
    return "".join(w[0] for w in words)[:6].upper()


def fmt_timestamp(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ts


def fmt_symbol_value(value):
    text = json.dumps(value) if not isinstance(value, str) else value
    return text if len(text) <= 120 else text[:117] + "…"


def submitter_initials(name):
    words = (name or "").split()
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()


def cumulative_pass(runs_asc):
    """Cumulative verified fraction over the sweep sequence."""
    series, ok = [], 0
    for i, run in enumerate(runs_asc, start=1):
        ok += run["status"] == "VERIFIED"
        series.append(ok / i)
    return series


def spark_svg(series):
    """Small pass-rate sparkline as an SVG string (fixed 0..1 y-range)."""
    if not series:
        return ""
    if len(series) == 1:
        series = series * 2
    n = len(series)
    pts = " ".join(
        f"{(i / (n - 1)) * (SPARK_W - 2) + 1:.1f},{SPARK_H - 1 - v * (SPARK_H - 2):.1f}"
        for i, v in enumerate(series)
    )
    return (
        f'<svg width="{SPARK_W}" height="{SPARK_H}" viewBox="0 0 {SPARK_W} {SPARK_H}" style="display:block">'
        f'<polyline points="{pts}" fill="none" stroke="currentColor" '
        f'stroke-width="1.25" stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def chart_svg(runs_asc):
    """Overview chart: cumulative pass rate with per-sweep verdict dots."""
    series = cumulative_pass(runs_asc)
    if not series:
        return ""
    plot = series * 2 if len(series) == 1 else series
    n = len(plot)
    x = lambda i: CHART_P + (i / (n - 1)) * (CHART_W - 2 * CHART_P)
    y = lambda v: CHART_H - CHART_P - v * (CHART_H - 2 * CHART_P)

    grid = "".join(
        f'<line x1="{CHART_P}" x2="{CHART_W - CHART_P}" y1="{y(g):.1f}" y2="{y(g):.1f}" class="chart-grid"/>'
        f'<text x="{CHART_P - 6}" y="{y(g) + 3:.1f}" class="chart-tick" text-anchor="end">{g:.2f}</text>'
        for g in (0.0, 0.25, 0.5, 0.75, 1.0)
    )
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(plot))
    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(plot[i]):.1f}" r="2.5" '
        f'class="chart-dot chart-dot--{"pred" if run["status"] == "VERIFIED" else "actual"}">'
        f"<title>sweep {run['id']} · {run['status']}</title></circle>"
        for i, run in enumerate(runs_asc[: len(plot)])
    )
    return (
        f'<svg viewBox="0 0 {CHART_W} {CHART_H}" class="chart-svg" preserveAspectRatio="none">'
        f'{grid}<path d="{path}" class="chart-line chart-line--pred"/>{dots}</svg>'
    )


def describe_aggregation(strategy):
    if not strategy:
        return "unspecified"
    kind = strategy.get("type", "unspecified")
    if kind == "all":
        return "all sweeps must pass to verify this claim"
    if kind == "fraction":
        threshold = strategy.get("parameters", {}).get("threshold", 0)
        return f"requires a {threshold * 100:.0f}% sweep pass rate to verify this claim"
    return kind


def normalize_links(raw_links):
    links = []
    for link in raw_links or []:
        if isinstance(link, str):
            url, title, kind = link, None, "link"
        else:
            url = link.get("url", "")
            title = link.get("title")
            kind = link.get("type", "link")
        if not url:
            continue
        if not title:
            lowered = url.lower()
            title = (
                "GitHub" if "github.com" in lowered
                else "Hugging Face" if "huggingface.co" in lowered
                else "External link"
            )
        links.append({"url": url, "title": title, "kind": kind})
    return links


def theory_links(theory, provenance):
    """Preserve relation types and resolve recorded source links when available."""
    rows = []
    sources = provenance.get("theory_sources") or {}
    for group in ("statement_links", "premise_links"):
        for link in theory.get(group, []):
            row = dict(link, group=group)
            source = sources.get(link.get("file"), {})
            url = source.get("url", "") if isinstance(source, dict) else source
            if url and link.get("line"):
                url += f'#L{link["line"]}'
            row["url"] = url
            rows.append(row)
    return rows


def enrich_card(entry):
    """Attach the derived fields the UI binds to (in place)."""
    card = entry["card"]
    runs = entry["runs"]  # newest first
    runs_asc = sorted(runs, key=lambda r: r.get("timestamp", ""))

    for run in runs:
        run["ok"] = run["status"] == "VERIFIED"
        run["time_str"] = fmt_timestamp(run.get("timestamp")) or "no timestamp"
        run["symbols_rows"] = [
            {"name": name, "value": fmt_symbol_value(value)}
            for name, value in (run.get("symbols") or {}).items()
        ]
        labels = [label for label, variant in entry.get("variants", {}).items()
                  if run["id"] in variant.get("claims", [])]
        run["variant_labels"] = labels
        run["label"] = "; ".join(labels) or run["id"]
        node = (card.get("kwdagger") or {}).get("result_node")
        prefix = f"metrics.{node}." if node else None
        run["measurement_rows"] = [
            {"name": key[len(prefix):], "value": fmt_symbol_value(value)}
            for key, value in (run.get("evidence") or {}).items()
            if prefix and key.startswith(prefix)
        ]

    n_runs = len(runs)
    n_verified = sum(run["ok"] for run in runs)
    series = cumulative_pass(runs_asc)

    submitter = card.get("submitter") or {}
    pipeline_steps = [
        {
            "step": step_name,
            "executable": (step or {}).get("executable", ""),
            "rows": (
                [
                    {"key": f"algo_params.{k}", "value": fmt_symbol_value(v)}
                    for k, v in ((step or {}).get("algo_params") or {}).items()
                ]
                + [
                    {"key": f"out_paths.{k}", "value": fmt_symbol_value(v)}
                    for k, v in ((step or {}).get("out_paths") or {}).items()
                ]
            ),
        }
        for step_name, step in (card.get("pipeline") or {}).items()
    ]

    entry.update(
        short=entry["organization"],
        summary=(card.get("description") or "").strip().splitlines()[0] if card.get("description") else "",
        version=str(card.get("version", "—")),
        submitter=submitter.get("name"),
        submitter_email=submitter.get("email"),
        submitter_initials=submitter_initials(submitter.get("name")),
        n_runs=n_runs,
        n_verified=n_verified,
        n_falsified=n_runs - n_verified,
        pass_rate=round(100 * n_verified / n_runs) if n_runs else 0,
        last_run=fmt_timestamp(runs_asc[-1].get("timestamp")) if runs_asc else None,
        spark_svg=spark_svg(series),
        chart_svg=chart_svg(runs_asc),
        agg_label=describe_aggregation(entry.get("claim_aggregation_strategy")),
        card_yaml=yaml.safe_dump(card, sort_keys=False, allow_unicode=True),
        links=normalize_links(card.get("links")),
        tag_list=(
            [{"label": t, "group": "tags"} for t in card.get("tags", [])]
            + [{"label": entry["organization"], "group": "organization"}]
            + [{"label": entry["milestone"], "group": "milestone"}]
        ),
        meta_chips=(
            [{"label": f"v{card.get('version')}", "group": "version"}] if card.get("version") is not None else []
        )
        + [{"label": org, "group": "organization"} for org in card.get("organizations", [])],
        card_symbols_rows=[
            {
                "name": name,
                "type": (spec or {}).get("type", ""),
                "value": fmt_symbol_value((spec or {}).get("value")),
            }
            for name, spec in (card.get("symbols") or {}).items()
        ],
        pipeline_steps=pipeline_steps,
    )
    return entry


# ---------------------------------------------------------------------------
# Artifact parsing (shared by directory scan and zip upload)
# ---------------------------------------------------------------------------

def parse_card_run(card_run, milestone, organization, algorithm=None):
    """Parse one ``{card_hash}_{timestamp}`` run directory, or None if the
    required artifacts (results/, card.yaml, verdict.json) are missing."""
    results_dir = card_run / "results"
    if not results_dir.exists():
        print(f"No results directory found in {card_run}")
        return None
    if not (card_run / "card.yaml").exists():
        print(f"No card definition found in {card_run}")
        return None
    if not (card_run / "verdict.json").exists():
        print(f"No verdict found in {card_run}")
        return None

    runs = []
    for sweep_dir in results_dir.iterdir():
        verdict_path = sweep_dir / "verdict.json"
        if not verdict_path.exists():
            continue
        result = json.loads(verdict_path.read_text())
        result["id"] = sweep_dir.name
        runs.append(result)
    runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

    card = yaml.safe_load((card_run / "card.yaml").read_text())
    # Fix latex-style double backticks in descriptions (TODO: proper handling)
    if "description" in card:
        card["description"] = re.sub(r"``([^`]*)``", r"`\1`", card["description"])

    claim = card.get("claim", {}).get("python", "")

    verdict_log = json.loads((card_run / "verdict.json").read_text())
    provenance = verdict_log.get("provenance") or {}
    theory_path = card_run / "theory.json"
    theory = json.loads(theory_path.read_text()) if theory_path.exists() else {}
    formalization = provenance.get("formalization") or {}
    variants_path = card_run / "variants.json"
    variants = json.loads(variants_path.read_text()) if variants_path.exists() else {}

    figures = None
    if (card_run / "kwdagger").exists():
        figure_paths = list((card_run / "kwdagger").glob("**/*.png"))
        if figure_paths:
            figures = [
                "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("utf-8")
                for path in figure_paths
            ]

    log_text = (card_run / "log").read_text() if (card_run / "log").exists() else "No log file found."

    entry = {
        "milestone": milestone,
        "organization": card.get("organizations", [organization])[0],
        "algorithm": algorithm or card.get("title", card_run.name).replace(" ", "_"),
        "claim_aggregation_strategy": verdict_log.get("claim_aggregation_strategy"),
        "card": card,
        "claim": claim,
        "result": verdict_log["result"],
        "runs": runs,
        "log": log_text,
        "figures": figures,
        "provenance": provenance,
        "theory": theory,
        "formalization": formalization,
        "variants": variants,
        "metrics": verdict_log.get("metrics") or {},
        "metric_rows": [{"name": name, "value": fmt_symbol_value(value)}
                        for name, value in (verdict_log.get("metrics") or {}).items()],
        "has_theory": bool(theory),
        "theory_links": theory_links(theory, provenance),
        "has_formalization": bool(formalization or any(
            entry.get("formalization") for entry in theory.get("entries", [])
        )),
    }
    parts = card_run.name.split("_")
    entry["id"] = f"{milestone}/{organization}/{entry['algorithm']}/{card_run.name}"
    entry["date"] = "".join(parts[1:])
    return enrich_card(entry)


def find_eval_card_data(root_path):
    """Scan the triple-nested layout: milestone / organization / algorithm /
    {card_hash}_{timestamp}."""
    contents = []
    for milestone_dir in ub.Path(root_path).iterdir():
        if not milestone_dir.is_dir():
            continue
        for organization_dir in milestone_dir.iterdir():
            if not organization_dir.is_dir():
                continue
            for algorithm_dir in organization_dir.iterdir():
                if not algorithm_dir.is_dir():
                    continue
                for card_run in algorithm_dir.iterdir():
                    if not card_run.is_dir():
                        continue
                    entry = parse_card_run(
                        card_run, milestone_dir.name, organization_dir.name, algorithm_dir.name
                    )
                    if entry:
                        contents.append(entry)
    return contents


def find_upload_data(root_path):
    """Parse native MAGNET output (a directory of run folders)."""
    contents = []
    for card_run in ub.Path(root_path).iterdir():
        if not card_run.is_dir():
            continue
        entry = parse_card_run(card_run, "SelfEvaluation", "Local")
        if entry:
            contents.append(entry)
    return contents


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

@TrameApp()
class EvaluationCardsApp:
    def __init__(self, path, server=None):
        self.server = get_server(server, client_type="vue3")
        self.state, self.ctrl = self.server.state, self.server.controller
        self.state.trame__title = "MAGNET — Evaluation Cards"
        icon_data_uri = "data:image/png;base64," + base64.b64encode(
            FAVICON_PATH.read_bytes()
        ).decode("utf-8")
        self.state.trame__favicon = icon_data_uri
        self.state.brand_mark_src = icon_data_uri

        self.state.is_local_deployment = "SPACE_ID" not in os.environ

        # View state
        self.state.view = "list"  # list | detail
        self.state.layout_mode = "grid"  # grid | list
        self.state.selected_card = None
        self.state.current_tab = "overview"
        self.state.show_python_claim = False
        self.state.show_raw_yaml = False
        self.state.expanded_symbols_runs = []
        self.state.expanded_pipeline_steps = []

        # Filter state
        self.state.search_term = ""
        self.state.selected_filters = {
            g["key"]: list(DEFAULT_FILTERS.get(g["key"], [])) for g in FILTER_GROUPS
        }
        self.state.active_chips = [
            {"key": key, "value": v}
            for key, values in self.state.selected_filters.items()
            for v in values
        ]

        # Upload feedback
        self.state.upload_show = False
        self.state.upload_msg = ""
        self.state.upload_color = "success"

        # Data
        self.state.cards = find_eval_card_data(path)
        self.state.filtered_cards = self.filter_cards(
            self.state.cards, self.state.search_term, self.state.selected_filters
        )
        self._refresh_catalog()

        build_layout(self)

    # -- catalog ------------------------------------------------------------

    def _refresh_catalog(self):
        """Rebuild filter groups (values) and topbar totals from the full card set."""
        cards = self.state.cards
        self.state.filter_groups = [
            {**group, "values": self._values_for(group["key"], cards)} for group in FILTER_GROUPS
        ]
        # self.state.n_verified_total = sum(c["result"] == "VERIFIED" for c in cards)
        # self.state.n_falsified_total = sum(c["result"] == "FALSIFIED" for c in cards)
        self._refresh_filter_counts(self.state.search_term, self.state.selected_filters)

    def _refresh_filter_counts(self, search_term, selected_filters):
        """Per-value filter counts, faceted against the current search term
        and every *other* group's active filters (so picking a value in one
        group updates the counts shown in the other groups, while a group's
        own counts stay stable as you pick more values within it)."""
        counts = {}
        for group in self.state.filter_groups:
            key = group["key"]
            other_filters = {k: v for k, v in selected_filters.items() if k != key}
            base = self.filter_cards(self.state.cards, search_term, other_filters)
            counts[key] = {v: sum(self._card_has(c, key, v) for c in base) for v in group["values"]}
        self.state.filter_counts = counts

    @staticmethod
    def _values_for(key, cards):
        if key == "tags":
            out = set()
            for c in cards:
                out.update(c["card"].get("tags", []))
            return sorted(out)
        return sorted({c[key] for c in cards})

    @staticmethod
    def _card_has(card, key, value):
        if key == "tags":
            return value in card["card"].get("tags", [])
        return card[key] == value

    # -- filtering ----------------------------------------------------------

    def filter_cards(self, cards, search_term, selected_filters):
        filtered = cards
        if search_term:
            needle = search_term.lower()
            filtered = [
                c for c in filtered
                if needle in c["card"]["title"].lower()
                or needle in c["algorithm"].lower()
                or needle in (c["card"].get("description") or "").lower()
            ]
        for key, wanted in selected_filters.items():
            if wanted:
                filtered = [c for c in filtered if any(self._card_has(c, key, v) for v in wanted)]
        return filtered

    @change("search_term", "selected_filters")
    def on_filter_change(self, search_term, selected_filters, **_):
        self.state.filtered_cards = self.filter_cards(self.state.cards, search_term, selected_filters)
        self.state.active_chips = [
            {"key": key, "value": v}
            for key, values in selected_filters.items()
            for v in values
        ]
        self._refresh_filter_counts(search_term, selected_filters)
        # Deselect the open card if it dropped out of the filtered set
        if self.state.selected_card and not any(
            c["id"] == self.state.selected_card["id"] for c in self.state.filtered_cards
        ):
            self.state.selected_card = None
            self.state.view = "list"

    def toggle_filter(self, key, value):
        current = dict(self.state.selected_filters)
        values = list(current.get(key, []))
        if value in values:
            values.remove(value)
        else:
            values.append(value)
        current[key] = values
        self.state.selected_filters = current

    def add_filter(self, key, value):
        """Add (never remove) a filter — used by clickable tag chips."""
        values = self.state.selected_filters.get(key, [])
        if value not in values:
            self.toggle_filter(key, value)
        self.state.view = "list"

    def clear_filters(self):
        self.state.search_term = ""
        self.state.selected_filters = {g["key"]: [] for g in FILTER_GROUPS}

    # -- navigation ---------------------------------------------------------

    def select_card(self, card_id):
        card = next((c for c in self.state.cards if c["id"] == card_id), None)
        if card is None:
            return
        self.state.selected_card = card
        self.state.view = "detail"
        self.state.current_tab = "overview"
        self.state.show_python_claim = False
        self.state.show_raw_yaml = False
        self.state.expanded_symbols_runs = []
        self.state.expanded_pipeline_steps = []

    def toggle_symbols(self, run_id):
        expanded = list(self.state.expanded_symbols_runs)
        if run_id in expanded:
            expanded.remove(run_id)
        else:
            expanded.append(run_id)
        self.state.expanded_symbols_runs = expanded

    def toggle_pipeline_step(self, step):
        expanded = list(self.state.expanded_pipeline_steps)
        if step in expanded:
            expanded.remove(step)
        else:
            expanded.append(step)
        self.state.expanded_pipeline_steps = expanded

    # -- upload -------------------------------------------------------------

    @change("uploaded_file")
    def handle_file_upload(self, uploaded_file, **_):
        if not uploaded_file:
            return  # Triggered when the user clears the input
        try:
            file_bytes = uploaded_file.get("content")
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zip_ref:
                    zip_ref.extractall(temp_dir)
                new_cards = find_upload_data(temp_dir)

            if new_cards:
                self.state.cards = self.state.cards + new_cards
                self._refresh_catalog()
                self.state.filtered_cards = self.filter_cards(
                    self.state.cards, self.state.search_term, self.state.selected_filters
                )
                self.state.upload_msg = f"Loaded {len(new_cards)} evaluation card(s)."
                self.state.upload_color = "success"
            else:
                self.state.upload_msg = "No valid evaluation cards found in the zip."
                self.state.upload_color = "warning"
        except Exception as exc:  # noqa: BLE001 — surface any parse error to the user
            self.state.upload_msg = f"Upload failed: {exc}"
            self.state.upload_color = "error"
        finally:
            self.state.upload_show = True
            self.state.uploaded_file = None

    # -- server -------------------------------------------------------------

    def start(self, **kwargs):
        self.server.start(**kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize Evaluation Card Runs")
    parser.add_argument("path", type=str, help="Path to evaluation card results directory")
    args, _ = parser.parse_known_args()
    app = EvaluationCardsApp(args.path)
    app.start()

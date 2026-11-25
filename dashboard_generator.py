import html
import math
from pathlib import Path

import pandas as pd


THEMES = {
    "Ruby & Amber": {
        "background": "#fffaf6",
        "surface": "#ffffff",
        "ink": "#38262a",
        "muted": "#806d6d",
        "primary": "#9f263b",
        "accent": "#ec9a24",
        "soft": "#fff0df",
        "line": "#f0e2d9",
        "chart": ["#b52e46", "#e58a31", "#efbd46", "#785369", "#d56c54"],
    },
    "Ocean Blue": {
        "background": "#f5faff",
        "surface": "#ffffff",
        "ink": "#1e3448",
        "muted": "#668095",
        "primary": "#176b9a",
        "accent": "#35a9ba",
        "soft": "#e6f4fb",
        "line": "#dceaf2",
        "chart": ["#1676a5", "#38a9bb", "#6dbf9e", "#f0b64b", "#687fb5"],
    },
    "Forest Green": {
        "background": "#f6fbf7",
        "surface": "#ffffff",
        "ink": "#24372c",
        "muted": "#708579",
        "primary": "#26724d",
        "accent": "#b2a34a",
        "soft": "#eaf5ed",
        "line": "#dfece2",
        "chart": ["#26724d", "#55a875", "#a9bb59", "#e4a443", "#487e84"],
    },
    "Violet & Rose": {
        "background": "#fbf8ff",
        "surface": "#ffffff",
        "ink": "#332b45",
        "muted": "#817791",
        "primary": "#704ca0",
        "accent": "#d87593",
        "soft": "#f3edfb",
        "line": "#e9e1f1",
        "chart": ["#704ca0", "#aa6ab5", "#db7790", "#eab05b", "#6285b3"],
    },
    "Slate & Teal": {
        "background": "#f6f9fa",
        "surface": "#ffffff",
        "ink": "#28383d",
        "muted": "#718287",
        "primary": "#315d67",
        "accent": "#36a69a",
        "soft": "#e8f4f2",
        "line": "#dfe9e9",
        "chart": ["#315d67", "#36a69a", "#77b786", "#d8a44d", "#687eb1"],
    },
}


def _escape(value):
    return html.escape(str(value), quote=True)


def _format_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:,.1f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:,.1f}K"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _markdown_to_html(markdown_text):
    blocks = []
    current_list = []

    def flush_list():
        if current_list:
            items = "".join(f"<li>{_escape(item)}</li>" for item in current_list)
            blocks.append(f"<ul>{items}</ul>")
            current_list.clear()

    for raw_line in (markdown_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            flush_list()
            continue
        if line.startswith("#"):
            flush_list()
            level = min(len(line) - len(line.lstrip("#")), 3)
            text = line.lstrip("#").strip()
            blocks.append(f"<h{level + 1}>{_escape(text)}</h{level + 1}>")
        elif line.startswith(("- ", "* ", "+ ")):
            current_list.append(line[2:])
        elif len(line) > 2 and line[0].isdigit() and line[1:3] in {". ", ") "}:
            flush_list()
            blocks.append(f"<p>{_escape(line)}</p>")
        else:
            flush_list()
            blocks.append(f"<p>{_escape(line)}</p>")
    flush_list()
    return "\n".join(blocks) or "<p>Analysis report is ready.</p>"


def _table_preview(name, dataframe):
    visible = dataframe.head(8)
    headings = "".join(f"<th>{_escape(column)}</th>" for column in visible.columns)
    rows = []
    for _, row in visible.iterrows():
        cells = "".join(
            f"<td>{_escape('' if pd.isna(value) else value)}</td>"
            for value in row
        )
        rows.append(f"<tr>{cells}</tr>")
    if not rows:
        rows.append(f'<tr><td colspan="{max(1, len(visible.columns))}">No rows</td></tr>')
    return (
        f'<section class="table-card"><h3>{_escape(name)}</h3>'
        f'<div class="table-scroll"><table><thead><tr>{headings}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f'<p class="caption">Showing {len(visible):,} of {len(dataframe):,} rows</p>'
        "</section>"
    )


def _bar_chart(name, dataframe, value_column, palette):
    numeric_columns = list(dataframe.select_dtypes(include="number").columns)
    category_columns = [
        column for column in dataframe.columns if column not in numeric_columns
    ]
    if dataframe.empty:
        return (
            '<section class="chart-card"><h3>Visual analysis</h3>'
            '<div class="chart-empty">This dataset has no chartable rows.</div></section>'
        )

    if category_columns:
        preferred_dimensions = (
            "region", "category", "product", "channel", "segment", "customer",
            "department", "type", "country", "store",
        )
        category_column = next(
            (
                column
                for hint in preferred_dimensions
                for column in category_columns
                if hint in str(column).casefold()
            ),
            category_columns[0],
        )
        chart_data = dataframe[[category_column, value_column]].copy()
        chart_data[value_column] = pd.to_numeric(
            chart_data[value_column], errors="coerce"
        )
        chart_data = chart_data.dropna(subset=[value_column])
        if chart_data.empty:
            return ""
        chart_data[category_column] = (
            chart_data[category_column].fillna("(missing)").astype(str)
        )
        grouped = (
            chart_data.groupby(category_column, dropna=False)[value_column]
            .sum()
            .sort_values(ascending=False)
            .head(8)
            .sort_values()
        )
        labels = [str(label) for label in grouped.index]
        values = [float(value) for value in grouped.values]
        chart_title = (
            f"{str(value_column).replace('_', ' ').title()} by "
            f"{str(category_column).replace('_', ' ').title()}"
        )
        series_label = name
    else:
        values_series = pd.to_numeric(dataframe[value_column], errors="coerce").dropna()
        values_series = values_series.tail(10)
        labels = [f"Row {index + 1}" for index in range(len(values_series))]
        values = [float(value) for value in values_series.values]
        chart_title = f"{str(value_column).replace('_', ' ').title()} across sampled rows"
        series_label = name

    if not values:
        return ""

    maximum = max(abs(value) for value in values) or 1.0
    row_height = 37
    chart_height = max(120, row_height * len(values) + 24)
    bars = []
    for index, (label, value) in enumerate(zip(labels, values)):
        y = 16 + index * row_height
        width = max(2, 450 * abs(value) / maximum)
        color = palette["chart"][index % len(palette["chart"])]
        bars.append(
            f'<text x="0" y="{y + 15}" class="axis-label">{_escape(label[:30])}</text>'
            f'<rect x="150" y="{y}" width="{width:.1f}" height="22" rx="6" fill="{color}"/>'
            f'<text x="{min(610, 160 + width):.1f}" y="{y + 15}" class="value-label">'
            f'{_escape(_format_number(value))}</text>'
        )
    return (
        '<section class="chart-card"><div class="card-title-row">'
        f"<div><h3>{_escape(chart_title)}</h3>"
        f'<p class="caption">Grouped sum · source: {_escape(series_label)}</p></div>'
        "</div>"
        f'<div class="chart-scroll"><svg viewBox="0 0 760 {chart_height}" role="img" '
        f'aria-label="{_escape(chart_title)}">{ "".join(bars) }</svg></div>'
        "</section>"
    )


def _charts(datasets, palette, chart_limit=8):
    charts = []
    measure_count = 0
    for name, dataframe in datasets.items():
        numeric_columns = list(dataframe.select_dtypes(include="number").columns)
        measure_count += len(numeric_columns)
        for column in numeric_columns:
            if len(charts) >= chart_limit:
                break
            chart = _bar_chart(name, dataframe, column, palette)
            if chart:
                charts.append(chart)
        if len(charts) >= chart_limit:
            break
    return charts, measure_count


def generate_dashboard_html(
    filename,
    datasets,
    analyses,
    report,
    theme_name="Ruby & Amber",
    focus="General business overview",
):
    palette = THEMES.get(theme_name, THEMES["Ruby & Amber"])
    profiles = list(analyses.values())
    row_count = sum(profile.get("rows", 0) for profile in profiles)
    column_count = sum(profile.get("columns", 0) for profile in profiles)
    missing_count = sum(profile.get("missing_total", 0) for profile in profiles)
    duplicate_count = sum(profile.get("duplicate_rows", 0) for profile in profiles)
    file_label = Path(filename).name

    kpis = [
        ("Rows analyzed", f"{row_count:,}"),
        ("Fields profiled", f"{column_count:,}"),
        ("Missing values", f"{missing_count:,}"),
        ("Duplicate rows", f"{duplicate_count:,}"),
    ]
    kpi_cards = "".join(
        f'<article class="kpi"><span>{_escape(label)}</span>'
        f"<strong>{_escape(value)}</strong></article>"
        for label, value in kpis
    )
    tables = "".join(
        _table_preview(name, dataframe) for name, dataframe in datasets.items()
    )
    if not tables:
        tables = (
            '<section class="table-card"><h3>Source content</h3>'
            f'<p class="caption">{_escape(file_label)} was analyzed as a document. '
            "The source text and visual definitions informed the report.</p></section>"
        )

    charts, measure_count = _charts(datasets, palette)
    chart_markup = "".join(charts)
    if not chart_markup:
        chart_markup = (
            '<section class="chart-card"><h3>Visual analysis</h3>'
            '<div class="chart-empty">Upload spreadsheet data with numeric columns '
            "to build charts from its values.</div></section>"
        )
    if measure_count > len(charts) and len(charts) == 8:
        chart_markup += (
            '<p class="caption chart-note">Showing the first '
            f'{len(charts)} charts. Complete numeric profiles remain available below.</p>'
        )
    encoded_report = _markdown_to_html(report)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="insightai-theme" content="{_escape(theme_name)}">
<title>{_escape(file_label)} · Insight Studio</title>
<style>
:root{{--bg:{palette["background"]};--surface:{palette["surface"]};--ink:{palette["ink"]};
--muted:{palette["muted"]};--primary:{palette["primary"]};--accent:{palette["accent"]};
--soft:{palette["soft"]};--line:{palette["line"]};}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.55 Inter,"Segoe UI",Arial,sans-serif}}
.wrap{{max-width:1220px;margin:0 auto;padding:28px 30px 48px}}
.top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;
color:var(--muted);font-size:12px}} .brand{{font-weight:800;color:var(--primary);font-size:14px}}
.hero{{position:relative;overflow:hidden;padding:28px 32px;border-radius:20px;color:white;
background:linear-gradient(108deg,var(--primary),color-mix(in srgb,var(--primary),var(--accent) 45%),var(--accent));
box-shadow:0 12px 30px color-mix(in srgb,var(--primary),transparent 82%)}}
.eyebrow{{font-size:10px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;opacity:.85}}
.hero h1{{font-size:clamp(23px,3vw,34px);line-height:1.15;margin:7px 0}}
.hero p{{margin:0;color:#fff4e8;max-width:760px}} .hero-meta{{margin-top:16px;display:flex;gap:8px;flex-wrap:wrap}}
.pill{{border:1px solid #ffffff70;background:#ffffff20;border-radius:20px;padding:4px 10px;font-size:10px}}
.section-head{{display:flex;justify-content:space-between;align-items:end;margin:24px 0 11px}}
h2{{font-size:17px;margin:0}} h3{{font-size:14px;margin:0 0 8px}}
.caption{{font-size:11px;color:var(--muted);margin:4px 0 0}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
.kpi,.chart-card,.table-card,.report{{background:var(--surface);border:1px solid var(--line);
border-radius:15px;box-shadow:0 6px 20px color-mix(in srgb,var(--ink),transparent 95%)}}
.kpi{{padding:16px}} .kpi span{{display:block;color:var(--muted);font-size:11px}}
.kpi strong{{display:block;font-size:24px;margin-top:8px;color:var(--primary)}}
.chart-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px}}
.chart-card,.table-card,.report{{padding:18px;margin-top:0}} .chart-note{{grid-column:1/-1}}
.chart-scroll,.table-scroll{{overflow:auto}} svg{{width:100%;min-width:560px;height:auto}}
.axis-label{{fill:var(--muted);font-size:12px}} .value-label{{fill:var(--ink);font-size:11px;font-weight:700}}
.chart-empty{{padding:26px 8px;text-align:center;color:var(--muted);font-size:12px}}
table{{width:100%;border-collapse:collapse;font-size:11px}} th,td{{text-align:left;padding:8px 9px;
border-bottom:1px solid var(--line);max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
th{{color:var(--muted);font-weight:700;background:var(--soft)}} .report h2,.report h3,.report h4{{margin-top:20px}}
.report h2{{font-size:16px;color:var(--primary)}} .report h3{{font-size:14px}}
.report p,.report li{{color:var(--ink);font-size:12px}} .report li{{margin:5px 0}}
.tables-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 14px}}
.footer{{padding-top:22px;text-align:center;color:var(--muted);font-size:10px}}
@media(max-width:800px){{.wrap{{padding:16px}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
.chart-grid,.tables-grid{{grid-template-columns:1fr}}.hero{{padding:23px}}}}
</style>
</head>
<body>
<main class="wrap">
<div class="top"><div class="brand">✦ Insight Studio</div><div>Business analysis · {_escape(theme_name)} theme</div></div>
<header class="hero"><div class="eyebrow">Your data, made useful</div>
<h1>From raw numbers to a clearer next move.</h1>
<p>Evidence-led analysis of <strong>{_escape(file_label)}</strong>, focused on {_escape(focus)}.</p>
<div class="hero-meta"><span class="pill">{_escape(file_label)}</span>
<span class="pill">{len(analyses)} dataset(s)</span><span class="pill">Decision-ready insights</span></div>
</header>
<div class="section-head"><div><h2>At a glance</h2><p class="caption">Coverage and data quality indicators</p></div></div>
<section class="grid">{kpi_cards}</section>
<div class="section-head"><div><h2>Explore the data</h2>
<p class="caption">Charts use values extracted from your source data.</p></div></div>
<section class="chart-grid">{chart_markup}
<section class="table-card"><h3>Data quality snapshot</h3>
<table><thead><tr><th>Dataset</th><th>Rows</th><th>Fields</th><th>Missing</th></tr></thead><tbody>
{''.join(f'<tr><td>{_escape(name)}</td><td>{profile.get("rows", 0):,}</td><td>{profile.get("columns", 0):,}</td><td>{profile.get("missing_total", 0):,}</td></tr>' for name, profile in analyses.items()) or '<tr><td colspan="4">Document source — see report details</td></tr>'}
</tbody></table></section>
<div class="section-head"><div><h2>Source tables</h2><p class="caption">Preview of the extracted datasets</p></div></div>
<section class="tables-grid">{tables}</section>
<div class="section-head"><div><h2>AI analysis and recommendations</h2>
<p class="caption">Generated from the calculated profiles and extracted document content.</p></div></div>
<article class="report">{encoded_report}</article>
<footer class="footer">Generated by Insight Studio · Theme: {_escape(theme_name)}</footer>
</main></body></html>"""

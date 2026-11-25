import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd


SUPPORTED_EXTENSIONS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".pdf",
    ".docx",
    ".pptx",
    ".pbix",
    ".pbit",
    ".txt",
    ".md",
}


def _is_missing(value):
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def load_tabular_data(file_bytes, filename):
    extension = Path(filename).suffix.lower()
    content = io.BytesIO(file_bytes)

    if extension == ".csv":
        try:
            dataframe = pd.read_csv(content)
        except UnicodeDecodeError:
            content.seek(0)
            dataframe = pd.read_csv(content, encoding="latin-1")
        if dataframe.empty and len(dataframe.columns) == 0:
            raise ValueError("The CSV file does not contain a header or data.")
        return {Path(filename).stem or "CSV": dataframe}

    if extension not in {".xlsx", ".xls"}:
        raise ValueError(f"{extension or 'This file'} is not a spreadsheet.")

    try:
        raw_sheets = pd.read_excel(
            content,
            sheet_name=None,
            header=None,
        )
    except Exception as error:
        raise ValueError(f"Could not read the spreadsheet: {error}") from error

    extracted = _extract_excel_sections(raw_sheets)
    if extracted:
        return extracted

    content.seek(0)
    try:
        sheets = pd.read_excel(content, sheet_name=None)
    except Exception as error:
        raise ValueError(f"Could not read spreadsheet headers: {error}") from error

    sheets = {
        name: dataframe.dropna(axis=0, how="all").dropna(axis=1, how="all")
        for name, dataframe in sheets.items()
    }
    return {
        name: dataframe
        for name, dataframe in sheets.items()
        if not dataframe.empty
    }


def _extract_excel_sections(raw_sheets):
    extracted = {}
    for sheet_name, raw in raw_sheets.items():
        rows = list(raw.itertuples(index=False, name=None))
        header_rows = []
        for row_index, row in enumerate(rows):
            populated = [value for value in row if not _is_missing(value)]
            labels = [
                value for value in populated
                if isinstance(value, str) and value.strip()
            ]
            if len(populated) < 2 or len(labels) / len(populated) < 0.7:
                continue
            body = []
            for body_row in rows[row_index + 1:]:
                if not any(not _is_missing(value) for value in body_row):
                    break
                body.append(body_row)
            has_numbers = any(
                isinstance(value, (int, float, np.number))
                and not isinstance(value, (bool, np.bool_))
                for body_row in body
                for value in body_row
                if not _is_missing(value)
            )
            if has_numbers:
                header_rows.append(row_index)

        used_names = set()
        for header_index, header_row in enumerate(header_rows):
            header = rows[header_row]
            columns = []
            for column_index, value in enumerate(header):
                if _is_missing(value) or not str(value).strip():
                    continue
                label = str(value).strip()
                original = label
                suffix = 2
                while label in {column for _, column in columns}:
                    label = f"{original} ({suffix})"
                    suffix += 1
                columns.append((column_index, label))
            if len(columns) < 2:
                continue

            end_index = len(rows)
            for next_header in header_rows[header_index + 1:]:
                if next_header > header_row:
                    end_index = next_header
                    break
            data_rows = []
            for row in rows[header_row + 1:end_index]:
                values = [row[index] for index, _ in columns]
                if not any(not _is_missing(value) for value in values):
                    break
                data_rows.append(values)
            if not data_rows:
                continue

            dataframe = pd.DataFrame(
                data_rows,
                columns=[label for _, label in columns],
            ).dropna(axis=1, how="all")
            if dataframe.empty:
                continue

            section = None
            for prior_row in reversed(rows[:header_row]):
                values = [
                    str(value).strip()
                    for value in prior_row
                    if not _is_missing(value) and str(value).strip()
                ]
                if len(values) == 1:
                    section = values[0]
                    break
            label = f"{sheet_name} — {section}" if section else str(sheet_name)
            base_label = label
            duplicate = 2
            while label in used_names:
                label = f"{base_label} ({duplicate})"
                duplicate += 1
            used_names.add(label)
            extracted[label] = dataframe
    return extracted


def analyze_dataframe(dataframe):
    frame = dataframe.copy()
    rows, columns = frame.shape
    numeric = frame.select_dtypes(include="number")
    numeric_summary = {}
    categorical_summary = {}
    correlations = {}
    outliers = {}
    grouped_numeric = {}
    time_series = {}

    if not numeric.empty:
        numeric_summary = numeric.describe().replace(
            {np.nan: None, np.inf: None, -np.inf: None}
        ).round(3).to_dict()
        numeric_summary = {
            column: {
                key: (None if pd.isna(value) else float(value))
                for key, value in values.items()
            }
            for column, values in numeric_summary.items()
        }
        correlation_matrix = numeric.corr(numeric_only=True).round(3)
        correlations = {
            str(column): {
                str(index): (
                    None if pd.isna(value) else float(value)
                )
                for index, value in values.items()
            }
            for column, values in correlation_matrix.to_dict().items()
        }
        for column in numeric.columns:
            values = numeric[column].dropna()
            if values.empty:
                continue
            lower_quartile = values.quantile(0.25)
            upper_quartile = values.quantile(0.75)
            spread = upper_quartile - lower_quartile
            lower_bound = lower_quartile - 1.5 * spread
            upper_bound = upper_quartile + 1.5 * spread
            outliers[str(column)] = {
                "count": int(((values < lower_bound) | (values > upper_bound)).sum()),
                "lower_bound": float(lower_bound),
                "upper_bound": float(upper_bound),
            }

    for column in frame.columns:
        series = frame[column]
        if pd.api.types.is_numeric_dtype(series):
            continue
        counts = series.fillna("(missing)").astype(str).value_counts().head(12)
        categorical_summary[str(column)] = {
            str(label): int(count) for label, count in counts.items()
        }
        if not numeric.empty and 2 <= series.nunique(dropna=True) <= 20:
            grouped = frame.groupby(column, dropna=False)[list(numeric.columns)].agg(
                ["sum", "mean"]
            )
            grouped_numeric[str(column)] = {}
            for label, measures in grouped.head(12).iterrows():
                grouped_numeric[str(column)][str(label)] = {
                    str(metric): {
                        statistic: (
                            None
                            if pd.isna(measures[(metric, statistic)])
                            else round(float(measures[(metric, statistic)]), 3)
                        )
                        for statistic in ("sum", "mean")
                    }
                    for metric in numeric.columns
                }

        date_hints = ("date", "time", "period", "month", "year", "week")
        date_column = (
            pd.api.types.is_datetime64_any_dtype(series)
            or any(hint in str(column).casefold() for hint in date_hints)
        )
        if date_column:
            parsed_dates = pd.to_datetime(series, errors="coerce")
            if (
                parsed_dates.notna().sum() >= 3
                and parsed_dates.notna().mean() >= 0.75
                and parsed_dates.nunique() >= 2
            ):
                dated = frame.loc[parsed_dates.notna(), list(numeric.columns)].copy()
                dated["_period"] = (
                    parsed_dates.loc[parsed_dates.notna()]
                    .dt.to_period("M")
                    .astype(str)
                )
                trend = dated.groupby("_period").sum(numeric_only=True).tail(24)
                time_series[str(column)] = {
                    str(period): {
                        str(metric): round(float(value), 3)
                        for metric, value in values.items()
                    }
                    for period, values in trend.to_dict(orient="index").items()
                }

    return {
        "rows": int(rows),
        "columns": int(columns),
        "column_names": [str(column) for column in frame.columns],
        "data_types": {
            str(column): str(dtype) for column, dtype in frame.dtypes.items()
        },
        "missing_values": {
            str(column): int(count)
            for column, count in frame.isna().sum().items()
        },
        "missing_total": int(frame.isna().sum().sum()),
        "duplicate_rows": int(frame.duplicated().sum()),
        "numeric_summary": numeric_summary,
        "categorical_summary": categorical_summary,
        "grouped_numeric": grouped_numeric,
        "time_series": time_series,
        "outliers": outliers,
        "correlations": correlations,
    }


def _extract_pdf(file_bytes):
    import fitz

    document = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for index, page in enumerate(document, start=1):
        text = page.get_text("text").strip()
        if text:
            pages.append(f"[Page {index}]\n{text}")
    document.close()
    if not pages:
        raise ValueError(
            "No selectable text was found in the PDF. For scanned PDFs, run OCR "
            "or export the report to a searchable PDF first."
        )
    return "\n\n".join(pages)


def _extract_docx(file_bytes):
    from docx import Document

    document = Document(io.BytesIO(file_bytes))
    lines = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    for table_index, table in enumerate(document.tables, start=1):
        lines.append(f"[Table {table_index}]")
        lines.extend(
            " | ".join(cell.text.strip() for cell in row.cells)
            for row in table.rows
        )
    return "\n".join(lines)


def _extract_pptx(file_bytes):
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(file_bytes))
    lines = []
    for index, slide in enumerate(presentation.slides, start=1):
        slide_lines = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text.strip():
                slide_lines.append(shape.text.strip())
            if getattr(shape, "has_table", False):
                slide_lines.extend(
                    " | ".join(cell.text.strip() for cell in row.cells)
                    for row in shape.table.rows
                )
            if getattr(shape, "has_chart", False):
                chart = shape.chart
                for series in chart.series:
                    values = list(series.values)
                    categories = []
                    try:
                        categories = [str(category.label) for category in chart.plots[0].categories]
                    except (AttributeError, TypeError, ValueError):
                        pass
                    if categories and len(categories) == len(values):
                        points = ", ".join(
                            f"{category}: {value}"
                            for category, value in zip(categories, values)
                        )
                    else:
                        points = ", ".join(str(value) for value in values)
                    slide_lines.append(f"Chart {series.name}: {points}")
        if slide_lines:
            lines.append(f"[Slide {index}]\n" + "\n".join(slide_lines))
    return "\n\n".join(lines)


def _layout_visuals(layout):
    found = []
    for section in layout.get("sections", []):
        page_name = section.get("displayName") or section.get("name") or "Report page"
        for container in section.get("visualContainers", []):
            visual_type = "visual"
            title = ""
            fields = set()
            for key in ("config", "query", "dataTransforms"):
                raw = container.get(key)
                if not isinstance(raw, str):
                    continue
                try:
                    config = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if key == "config":
                    visual = config.get("singleVisual", {})
                    visual_type = visual.get("visualType", visual_type)
                    objects = visual.get("objects", {})
                    for title_item in objects.get("title", []):
                        title = title_item.get("properties", {}).get("text", {}).get("expr", {}).get("Literal", {}).get("Value", title)
                serialized = json.dumps(config, ensure_ascii=False)
                for field in ("queryRef", "displayName"):
                    marker = f'"{field}":"'
                    start = 0
                    while (position := serialized.find(marker, start)) >= 0:
                        value_start = position + len(marker)
                        value_end = serialized.find('"', value_start)
                        if value_end > value_start:
                            fields.add(serialized[value_start:value_end])
                        start = value_end + 1
            found.append(
                {
                    "page": str(page_name),
                    "visual": str(visual_type),
                    "title": str(title)[:180],
                    "fields": sorted(fields)[:20],
                }
            )
    return found


def _extract_powerbi(file_bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            layout_bytes = archive.read("Report/Layout")
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError(
            "This Power BI file does not contain a readable Report/Layout. "
            "For dependable data analysis, export its data to CSV/Excel or "
            "the report to PDF/PowerPoint."
        ) from error

    try:
        layout = json.loads(layout_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Could not decode the Power BI report layout.") from error

    visuals = _layout_visuals(layout)
    report_text = [
        "Power BI report layout metadata.",
        "PBIX embeds its semantic model in a proprietary VertiPaq format; "
        "this tool reads report pages and visual definitions, not the underlying "
        "model's row-level data.",
    ]
    report_text.extend(
        f"Page: {item['page']} | Visual: {item['visual']} | "
        f"Title: {item['title'] or '(untitled)'} | "
        f"Fields: {', '.join(item['fields']) or '(not exposed in layout)'}"
        for item in visuals
    )
    if not visuals:
        report_text.append(
            "No visual definitions were available in the layout metadata."
        )
    return "\n".join(report_text)


def extract_document(file_bytes, filename):
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return _extract_pdf(file_bytes)
    if extension == ".docx":
        return _extract_docx(file_bytes)
    if extension == ".pptx":
        return _extract_pptx(file_bytes)
    if extension in {".pbix", ".pbit"}:
        return _extract_powerbi(file_bytes)
    if extension in {".txt", ".md"}:
        try:
            return file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError(f"{filename} is not valid UTF-8 text.") from error
    raise ValueError(f"Unsupported file type: {extension or 'unknown'}")


def analyze_upload(file_bytes, filename):
    extension = Path(filename).suffix.lower()
    warnings = []
    if extension in {".csv", ".xlsx", ".xls"}:
        datasets = load_tabular_data(file_bytes, filename)
        if not datasets:
            raise ValueError("No non-empty worksheets or rows were found.")
        analyses = {
            name: analyze_dataframe(dataframe)
            for name, dataframe in datasets.items()
        }
        return datasets, analyses, "", warnings

    text = extract_document(file_bytes, filename)
    if not text.strip():
        raise ValueError(
            "No extractable text or chart data was found in this document."
        )
    if extension in {".pbix", ".pbit"}:
        warnings.append(
            "Power BI PBIX/PBIT import reads report layout and visual metadata. "
            "It cannot access the embedded VertiPaq data model; attach exported "
            "CSV/Excel data or a PDF/PowerPoint report for data-backed metrics."
        )
    return {}, {}, text, warnings


def build_analysis_context(datasets, analyses, document_text, filename, focus):
    context = {
        "file": filename,
        "analysis_focus": focus,
        "datasets": analyses,
        "sample_rows": {
            name: dataframe.head(5).to_dict(orient="records")
            for name, dataframe in datasets.items()
        },
        "document_text": document_text[:40000],
    }
    serialized = json.dumps(context, ensure_ascii=False, default=str)
    if len(serialized) > 50000:
        context["document_text"] = context["document_text"][:12000]
        for profile in context["datasets"].values():
            for key in ("categorical_summary", "correlations"):
                if key in profile:
                    profile[key] = dict(list(profile[key].items())[:12])
        serialized = json.dumps(context, ensure_ascii=False, default=str)
    return serialized[:50000]

import hashlib
import random
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from analyzer import analyze_upload, build_analysis_context
from dashboard_generator import THEMES, generate_dashboard_html
from llm_providers import (
    NVIDIA_NEMOTRON_MODEL,
    OLLAMA_NEMOTRON_MODEL,
    generate_report,
)
from report_generator import generate_docx, generate_pdf, html_to_pptx


SAMPLE_CSV = """date,region,revenue,cost,orders
2025-01,North,42800,29100,362
2025-02,North,46100,30200,388
2025-03,North,49300,31600,411
2025-01,South,35600,25200,309
2025-02,South,38200,26400,327
2025-03,South,41700,28100,354
2025-01,West,52400,33800,438
2025-02,West,50100,32900,421
2025-03,West,56800,35700,472
"""


def _nvidia_api_key_from_secrets():
    try:
        return st.secrets.get("NVIDIA_API_KEY")
    except StreamlitSecretNotFoundError:
        return None


st.set_page_config(
    page_title="Insight Studio | AI Data Analyst",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
:root {
  --cream:#fffaf6; --ink:#492f32; --muted:#907c7a; --line:#f0e2d9;
  --red:#b5223d; --red-dark:#781e30; --gold:#f3b12d;
}
html,body,[data-testid="stAppViewContainer"] {background:var(--cream);color:var(--ink)}
[data-testid="stHeader"] {background:transparent}
[data-testid="stToolbar"],#MainMenu,footer {visibility:hidden}
[data-testid="stAppViewContainer"]>.main .block-container,
[data-testid="stMainBlockContainer"] {
  width:100%!important;max-width:none!important;margin:0!important;
  padding:1rem clamp(1.25rem,3vw,2.25rem) 3rem!important;
}
[data-testid="stSidebar"] {background:linear-gradient(180deg,#681c2b,#8d2737);border:0;width:230px!important;min-width:230px!important}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {color:#fff7f1}
[data-testid="stSidebar"] p {color:#f2d9d4}
.brand {display:flex;align-items:center;gap:10px;padding:8px 4px 26px;color:white;font-weight:800;font-size:17px}
.brand-icon {display:grid;place-items:center;width:34px;height:34px;background:#ffd458;color:#70202e;border-radius:10px}
.side-label {font-size:9px;letter-spacing:.18em;color:#f0cbc4;font-weight:800;margin:0 4px 12px;text-transform:uppercase}
.step {display:flex;align-items:center;gap:10px;padding:10px;border-radius:10px;color:#f7e9e4;font-size:12px;margin:4px 0}
.step.active {background:#ffffff20;color:white;font-weight:700}
.step.done {color:#ffe188}
.step-no {display:grid;place-items:center;width:21px;height:21px;border:1px solid #ffffff70;border-radius:50%;font-size:9px}
.step.active .step-no {border-color:#ffd458;background:#ffd458;color:#70202e;font-weight:800}
.tip {margin-top:32vh;border:1px solid #ffffff45;border-radius:12px;padding:13px;font-size:10px;color:#f4d8d1;line-height:1.55}
.tip b {display:block;color:white;margin:5px 0}
.topbar {display:flex;justify-content:space-between;align-items:center;color:#826b67;font-size:11px;padding:0 0 12px;border-bottom:1px solid #f1e7e1;margin-bottom:22px}
.pill {display:inline-block;padding:6px 12px;border:1px solid #f1e7e1;border-radius:18px;background:white;color:#714f38;font-weight:650}
.eyebrow {color:#b8283b;font-size:10px;letter-spacing:.16em;font-weight:850;text-transform:uppercase;margin-bottom:5px}
.page-title {color:#432b30;font-size:31px;font-weight:760;line-height:1.15;margin:0}
.subtitle {color:var(--muted);font-size:13px;margin:7px 0 17px}
.hero {position:relative;overflow:hidden;border-radius:15px;padding:22px 26px;margin:0 0 18px;color:white;background:linear-gradient(110deg,#962337,#c43143 61%,#f0a421);box-shadow:0 8px 20px #a6463824}
.hero:after {content:"";position:absolute;right:26px;top:-40px;width:175px;height:175px;border-radius:50%;background:#ffffff1a}
.hero-kicker {color:#ffe7a2;font-size:9px;letter-spacing:.18em;font-weight:850}
.hero h2 {position:relative;z-index:1;margin:5px 0;font-size:20px;color:white}
.hero p {position:relative;z-index:1;max-width:640px;color:#ffede7;font-size:11px;margin:0}
.tags {display:flex;gap:6px;flex-wrap:wrap;margin-top:11px}
.tag {padding:3px 9px;border:1px solid #ffffff60;border-radius:20px;font-size:9px;color:white}
.panel-title {font-size:14px;color:#482d31;font-weight:750;margin:0 0 3px}
.panel-caption {font-size:10px;color:#9a817d;margin:0 0 14px}
.empty {display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;min-height:290px;padding:24px;background:white;border:1px solid var(--line);border-radius:15px}
.empty-icon {display:grid;place-items:center;width:100px;height:67px;border-radius:13px;background:#fff1dc;color:#c42d43;font-size:32px;margin-bottom:14px}
.empty b {font-size:14px;color:#4e3034}
.empty span {font-size:11px;color:#927d78;line-height:1.55;max-width:350px;margin-top:6px}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:var(--line);border-radius:14px;background:white;box-shadow:0 5px 18px #522a2310}
.stButton>button {border-radius:8px;border:0;background:#bd263e;color:white;font-size:12px;font-weight:700;min-height:40px}
.stButton>button:hover {background:#9e1e34;color:white}
.stDownloadButton>button {border-radius:8px;border:1px solid #eeddd5;background:white;color:#66383c;font-size:11px;font-weight:650}
[data-testid="stFileUploader"] {border:1px dashed #e2bdb2;border-radius:10px;padding:9px;background:#fffdfb}
[data-testid="stSelectbox"] label,[data-testid="stFileUploader"] label {color:#62484a;font-size:11px;font-weight:700}
[data-baseweb="select"]>div {background:#fff!important;color:var(--ink)!important;border-color:var(--line)!important}
[data-baseweb="select"] input {color:var(--ink)!important}
[data-baseweb="popover"] ul {background:#fff!important}
[data-baseweb="popover"] li {color:var(--ink)!important}
[data-testid="stAlert"] {border-radius:10px}
@media(max-width:850px) {
  [data-testid="stAppViewContainer"]>.main .block-container,
  [data-testid="stMainBlockContainer"] {padding:1rem!important}
  .page-title{font-size:26px}.tip{margin-top:18vh}
}
</style>
""",
    unsafe_allow_html=True,
)

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "sample_csv" not in st.session_state:
    st.session_state.sample_csv = SAMPLE_CSV


with st.sidebar:
    result = st.session_state.analysis_result
    has_result = bool(result)
    st.markdown(
        f"""
<div class="brand"><span class="brand-icon">▥</span><span>Insight Studio</span></div>
<div class="side-label">Workspace flow</div>
<div class="step {'done' if has_result else 'active'}"><span class="step-no">{'✓' if has_result else '01'}</span>Add your data</div>
<div class="step {'done' if has_result else ''}"><span class="step-no">{'✓' if has_result else '02'}</span>Choose analysis</div>
<div class="step {'active' if has_result else ''}"><span class="step-no">{'✓' if has_result else '03'}</span>Review insights</div>
<div class="step"><span class="step-no">04</span>Share report</div>
<div class="tip">✦<b>Make better decisions</b>Start with a sample CSV to see how business data becomes a clear action plan.</div>
""",
        unsafe_allow_html=True,
    )
    st.caption("Free local option: Nemotron 3 Nano 4B via Ollama.")
    st.caption("Model setup: `ollama pull nemotron-3-nano:4b`")

st.markdown(
    """
<div class="topbar"><span>Workspace / <b>Business analysis</b></span>
<span class="pill">Nemotron-powered workspace</span></div>
<div class="eyebrow">Analytics workspace</div>
<h1 class="page-title">Turn data into direction.</h1>
<p class="subtitle">Upload your numbers, choose a focus, and get a report you can act on.</p>
<div class="hero"><div class="hero-kicker">YOUR DATA, MADE USEFUL</div>
<h2>From raw numbers to a clearer next move.</h2>
<p>Explore an executive summary, compare trends across periods, and turn the highlights into a decision-ready report.</p>
<div class="tags"><span class="tag">CSV · Excel</span><span class="tag">Power BI · Documents</span><span class="tag">Charts · Recommendations</span></div>
</div>
""",
    unsafe_allow_html=True,
)

setup_column, results_column = st.columns([0.9, 1.65], gap="medium")

with setup_column:
    with st.container(border=True):
        st.markdown('<div class="panel-title">▤ &nbsp; Set up your analysis</div>', unsafe_allow_html=True)
        st.markdown('<p class="panel-caption">A few steps to a clearer picture.</p>', unsafe_allow_html=True)

        focus = st.selectbox(
            "1. What would you like to analyze?",
            [
                "Sales & finance",
                "Operations & supply chain",
                "Marketing performance",
                "Customer and product trends",
                "People and workforce",
                "General business overview",
            ],
            index=0,
        )
        uploaded = st.file_uploader(
            "2. Add your data",
            type=["csv", "xlsx", "xls", "pdf", "docx", "pptx", "pbix", "pbit", "txt", "md"],
            help="Power BI PBIX files provide visual/layout metadata; export data to CSV or Excel for full numeric analysis.",
        )
        st.caption("or paste CSV data below, or use the sample")
        sample_data = st.text_area(
            "CSV data",
            key="sample_csv",
            height=110,
            help="Include a header row followed by one data row per period or item.",
        )
        if st.button("↻ Use sample data", width="stretch"):
            st.session_state.sample_csv = SAMPLE_CSV
            st.rerun()

        with st.expander("AI model", expanded=False):
            provider = st.selectbox(
                "Choose a Nemotron option",
                ["Ollama (local Nemotron)", "NVIDIA hosted Nemotron"],
                index=1,
                help="Ollama runs locally at no API cost. NVIDIA-hosted API trial requires a key and may have usage limits.",
            )
            if provider == "Ollama (local Nemotron)":
                model_id = st.text_input(
                    "Ollama model",
                    value=OLLAMA_NEMOTRON_MODEL,
                    help="Pull it once with: ollama pull nemotron-3-nano:4b",
                )
                api_key = None
                st.caption("Free and private; response speed depends on your computer.")
            else:
                model_id = NVIDIA_NEMOTRON_MODEL
                st.caption("NVIDIA hosted model")
                st.code(NVIDIA_NEMOTRON_MODEL, language=None)
                api_key = st.text_input(
                    "NVIDIA API key",
                    type="password",
                    help="Optional if NVIDIA_API_KEY is configured in Streamlit secrets or the environment.",
                ) or _nvidia_api_key_from_secrets()
                st.caption(
                    "Nemotron 3.5 Super VL streams the report. Hosted trial has "
                    "usage limits; uploaded content is sent to NVIDIA."
                )

        has_upload = uploaded is not None
        has_csv = bool(sample_data.strip())
        source_bytes = uploaded.getvalue() if uploaded else sample_data.encode("utf-8")
        source_name = uploaded.name if uploaded else "sample_business_data.csv"
        source_marker = hashlib.sha256(source_bytes).hexdigest()
        previous_marker = st.session_state.get("last_source_marker")
        if (
            previous_marker is not None
            and previous_marker != source_marker
            and st.session_state.analysis_result is not None
        ):
            st.session_state.analysis_result = None
            st.session_state.last_source_marker = source_marker
            st.info("The source changed. Run a new analysis to refresh the dashboard.")
        run_analysis = st.button(
            "✦  Run analysis",
            type="primary",
            width="stretch",
            disabled=not (has_upload or has_csv),
        )

        if run_analysis:
            file_bytes = source_bytes
            filename = source_name
            try:
                with st.spinner("Extracting data and preparing evidence..."):
                    datasets, analyses, document_text, warnings = analyze_upload(
                        file_bytes,
                        filename,
                    )
                    context = build_analysis_context(
                        datasets,
                        analyses,
                        document_text,
                        filename,
                        focus,
                    )
                with st.spinner("Nemotron is writing your detailed analysis..."):
                    report = generate_report(
                        context,
                        focus=focus,
                        provider=provider,
                        model=model_id.strip(),
                        api_key=api_key,
                    )
                theme_name = random.choice(tuple(THEMES))
                dashboard_html = generate_dashboard_html(
                    filename,
                    datasets,
                    analyses,
                    report,
                    theme_name=theme_name,
                    focus=focus,
                )
                st.session_state.analysis_result = {
                    "filename": filename,
                    "datasets": datasets,
                    "analyses": analyses,
                    "document_text": document_text,
                    "warnings": warnings,
                    "report": report,
                    "dashboard_html": dashboard_html,
                    "theme": theme_name,
                    "focus": focus,
                    "context": context,
                }
                st.session_state.last_source_marker = source_marker
                st.rerun()
            except Exception as error:
                st.error(f"Analysis failed: {error}")
                if provider == "Ollama (local Nemotron)":
                    st.info(
                        "To start the free local model, install Ollama, run "
                        "`ollama pull nemotron-3-nano:4b`, then keep Ollama running."
                    )

with results_column:
    result = st.session_state.analysis_result
    if not result:
        st.markdown(
            """
<div class="empty"><div class="empty-icon">▥</div>
<b>Your insights will appear here</b>
<span>Upload a spreadsheet or document, or try the sample data, then run an analysis to see trends, highlights, charts and a practical report.</span></div>
""",
            unsafe_allow_html=True,
        )
    else:
        export_stem = f"{Path(result['filename']).stem}_Analysis_Report"
        st.markdown(
            f'<div class="panel-title">Analysis preview '
            f'<span class="pill">{result["theme"]} theme</span></div>'
            f'<p class="panel-caption">{result["filename"]} · Focus: {result["focus"]}</p>',
            unsafe_allow_html=True,
        )
        for warning in result["warnings"]:
            st.warning(warning)
        st.iframe(result["dashboard_html"], height=900)

        html_col, ppt_col, pdf_col, docx_col = st.columns(4)
        with html_col:
            st.download_button(
                "Download HTML",
                data=result["dashboard_html"],
                file_name=f"{export_stem}.html",
                mime="text/html",
                width="stretch",
            )
        with ppt_col:
            try:
                pptx_bytes = html_to_pptx(
                    result["dashboard_html"],
                    title=f"{Path(result['filename']).stem} analysis dashboard",
                    theme_name=result["theme"],
                )
                st.download_button(
                    "Download PowerPoint",
                    data=pptx_bytes,
                    file_name=f"{export_stem}.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    width="stretch",
                )
            except Exception as error:
                st.error(f"PowerPoint export failed: {error}")
        with pdf_col:
            st.download_button(
                "Download PDF",
                data=generate_pdf(
                    f"{Path(result['filename']).stem} Analysis Report",
                    result["report"],
                ),
                file_name=f"{export_stem}.pdf",
                mime="application/pdf",
                width="stretch",
            )
        with docx_col:
            st.download_button(
                "Download Word",
                data=generate_docx(
                    f"{Path(result['filename']).stem} Analysis Report",
                    result["report"],
                ),
                file_name=f"{export_stem}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch",
            )

        st.markdown("#### Complete analysis report")
        st.markdown(result["report"])
        if result["analyses"]:
            with st.expander("Calculated dataset profiles"):
                for name, profile in result["analyses"].items():
                    st.markdown(f"**{name}**")
                    st.json(profile)
            with st.expander("Extracted data preview"):
                for name, dataframe in result["datasets"].items():
                    st.markdown(f"**{name}**")
                    st.dataframe(dataframe.head(100), width="stretch")

st.divider()
with st.expander("HTML to PowerPoint converter"):
    st.write("Upload a standalone HTML dashboard to convert it into an editable PowerPoint summary.")
    html_upload = st.file_uploader(
        "HTML dashboard",
        type=["html", "htm"],
        key="html_to_ppt_upload",
    )
    if html_upload:
        try:
            uploaded_html = html_upload.getvalue().decode("utf-8-sig")
        except UnicodeDecodeError:
            st.error("The HTML file must be UTF-8 encoded.")
        else:
            try:
                converted = html_to_pptx(
                    uploaded_html,
                    title=html_upload.name.rsplit(".", 1)[0],
                )
                st.download_button(
                    "Download converted PowerPoint",
                    data=converted,
                    file_name=f"{html_upload.name.rsplit('.', 1)[0]}.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    key="download_converted_ppt",
                )
            except Exception as error:
                st.error(f"HTML conversion failed: {error}")

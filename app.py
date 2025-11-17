import io
import re
import streamlit as st
import pdfplumber
import pandas as pd

st.set_page_config(page_title="PDF to Table Extractor IDX", layout="wide")

st.title("IDX Keterbukaan Informasi PDF Extractor")
st.write(
    "Upload file **PDF** yang berisi tabel kepemilikan saham (lampiran IDX), "
    "aplikasi akan mencoba **deteksi header otomatis**, menormalkan nama kolom, "
    "lalu menyediakan **filter** berdasarkan kolom-kolom penting."
)

# ===============================
# UPLOADER PDF
# ===============================
uploaded_file = st.file_uploader("Upload file PDF", type=["pdf"])

col1, col2 = st.columns(2)
with col1:
    start_page = st.number_input(
        "Halaman mulai (1-based)",
        min_value=1,
        value=2,   # default mulai dari halaman 2
        step=1,
        help="Halaman pertama yang akan diproses. Gunakan angka 1 untuk halaman pertama."
    )
with col2:
    end_page = st.number_input(
        "Halaman akhir (1-based, boleh sama dengan mulai)",
        min_value=1,
        value=50,  # default besar → otomatis diklip ke halaman terakhir PDF
        step=1,
        help="Halaman terakhir yang akan diproses. Nilai besar akan otomatis diklip ke halaman terakhir."
    )

extract_button = st.button("🔍 Ekstrak Tabel")

# State hasil extract
if "tables" not in st.session_state:
    st.session_state.tables = []
    st.session_state.table_info = []  # (page, index_in_page)

# ===============================
# UTIL: Deteksi header otomatis
# ===============================
TARGET_HEADER_KEYWORDS = [
    "kode efek",
    "kode saham",
    "nama emiten",
    "emiten",
    "nama pemegang rekening efek",
    "pemegang rekening efek",
    "nama pemegang saham",
    "pemegang saham",
    "nama rekening efek",
    "rekening efek",
]

HEADER_CANONICAL_MAP = {
    "kode efek": "Kode Efek",
    "kode saham": "Kode Efek",
    "kode": "Kode Efek",
    "stock code": "Kode Efek",

    "nama emiten": "Nama Emiten",
    "emiten": "Nama Emiten",

    "nama pemegang rekening efek": "Nama Pemegang Rekening Efek",
    "pemegang rekening efek": "Nama Pemegang Rekening Efek",
    "pemegang rekening": "Nama Pemegang Rekening Efek",

    "nama pemegang saham": "Nama Pemegang Saham",
    "pemegang saham": "Nama Pemegang Saham",

    "nama rekening efek": "Nama Rekening Efek",
    "rekening efek": "Nama Rekening Efek",
}


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def make_unique_columns(cols):
    """
    Pastikan semua nama kolom unik dengan menambah suffix _1, _2, dst.
    """
    seen = {}
    new_cols = []
    for c in cols:
        base = c
        if base not in seen:
            seen[base] = 0
            new_cols.append(base)
        else:
            seen[base] += 1
            new_cols.append(f"{base}_{seen[base]}")
    return new_cols


def auto_detect_header(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Mencoba mendeteksi baris header terbaik di beberapa baris pertama.
    """
    if df_raw.empty:
        return df_raw

    max_rows_check = min(5, len(df_raw))
    candidates = df_raw.iloc[:max_rows_check]

    best_idx = candidates.index[0]
    best_score = -1

    for idx, row in candidates.iterrows():
        score = 0.0
        for cell in row:
            cell_text = normalize_text(cell)
            if cell_text:
                score += 0.5
                for kw in TARGET_HEADER_KEYWORDS:
                    if kw in cell_text:
                        score += 2.0
        if score > best_score:
            best_score = score
            best_idx = idx

    header_row = df_raw.loc[best_idx]
    new_cols = []
    for c in header_row:
        col_text = str(c) if c is not None else ""
        col_text = re.sub(r"\s+", " ", col_text).strip()
        if not col_text:
            col_text = "COL"
        new_cols.append(col_text)

    # Buat unik
    new_cols = make_unique_columns(new_cols)

    df = df_raw.copy()
    df.columns = new_cols
    df = df.loc[best_idx + 1 :].reset_index(drop=True)
    return df


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalisasi nama kolom menjadi bentuk kanonik:
    - Kode Efek
    - Nama Emiten
    - Nama Pemegang Rekening Efek
    - Nama Pemegang Saham
    - Nama Rekening Efek
    """
    col_map = {}
    for col in df.columns:
        norm = normalize_text(col)
        canonical = None

        if norm in HEADER_CANONICAL_MAP:
            canonical = HEADER_CANONICAL_MAP[norm]
        else:
            for key, target in HEADER_CANONICAL_MAP.items():
                if key in norm:
                    canonical = target
                    break

        if canonical:
            col_map[col] = canonical
        else:
            col_map[col] = col

    df = df.rename(columns=col_map)
    return df


# ===============================
# FUNGSI: Extract tabel PDF
# ===============================
def extract_tables_from_pdf(file_bytes, page_start, page_end):
    """
    Ekstrak tabel menggunakan pdfplumber + deteksi header otomatis.
    page_start, page_end: 1-based
    """
    tables = []
    info = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        num_pages = len(pdf.pages)

        page_start_idx = max(0, page_start - 1)
        page_end_idx = min(num_pages - 1, page_end - 1)

        for p in range(page_start_idx, page_end_idx + 1):
            page = pdf.pages[p]
            raw_tables = page.extract_tables()

            for idx, tbl in enumerate(raw_tables):
                if not tbl:
                    continue

                df_raw = pd.DataFrame(tbl)
                df_headered = auto_detect_header(df_raw)
                df_norm = normalize_column_names(df_headered)

                tables.append(df_norm)
                info.append((p + 1, idx + 1))

    return tables, info


# ===============================
# BENTUKKAN MULTI-LEVEL HEADER
# ===============================
def build_multilevel_header(df: pd.DataFrame):
    """
    Bangun header bertingkat:
    - Kolom yang namanya diawali 'Kepemilikan Per ' akan dianggap sebagai grup
      untuk 3 kolom berturut-turut:
         [Jumlah Saham, Saham Gabungan Per Investor, Persentase Kepemilikan Per Investor (%)]
    - Kolom lain: level atas = nama kolom, level bawah = ''.
    Return: df_multi, perubahan_key (key untuk kolom Perubahan di MultiIndex).
    """
    cols = list(df.columns)
    top = []
    bottom = []

    perubahan_key = None

    i = 0
    while i < len(cols):
        col = cols[i]

        if isinstance(col, str) and col.startswith("Kepemilikan Per "):
            # grup 3 kolom: i, i+1, i+2 (kalau ada)
            group_label = col
            sub_labels = [
                "Jumlah Saham",
                "Saham Gabungan Per Investor",
                "Persentase Kepemilikan Per Investor (%)",
            ]

            span = min(3, len(cols) - i)
            for j in range(span):
                top.append(group_label)
                bottom.append(sub_labels[j])
            i += span
            continue

        if col == "Perubahan":
            top.append("Perubahan")
            bottom.append("")
            perubahan_key = ("Perubahan", "")
            i += 1
            continue

        top.append(col)
        bottom.append("")
        i += 1

    multi_cols = pd.MultiIndex.from_arrays([top, bottom])
    df_multi = df.copy()
    df_multi.columns = multi_cols

    return df_multi, perubahan_key


# ===============================
# PROSES EKSTRAK
# ===============================
if uploaded_file is not None and extract_button:
    st.session_state.tables = []
    st.session_state.table_info = []

    file_bytes = uploaded_file.read()

    with st.spinner("Mengekstrak tabel dari PDF + deteksi header otomatis..."):
        try:
            tables, info = extract_tables_from_pdf(
                file_bytes=file_bytes,
                page_start=int(start_page),
                page_end=int(end_page),
            )
        except Exception as e:
            st.error(f"Gagal mengekstrak tabel: {e}")
            tables, info = [], []

    if not tables:
        st.warning("Tidak ada tabel yang berhasil diekstrak di rentang halaman tersebut.")
    else:
        st.success(f"Berhasil mengekstrak {len(tables)} tabel dari PDF.")
        st.session_state.tables = tables
        st.session_state.table_info = info

# ===============================
# TAMPILKAN TABEL + FILTER (SEMUA HALAMAN)
# ===============================
if st.session_state.tables:
    st.subheader("📊 Hasil Ekstraksi Tabel (Semua Halaman)")

    # Gabungkan semua tabel dari semua halaman
    try:
        df_selected = pd.concat(st.session_state.tables, ignore_index=True)
    except Exception:
        df_selected = st.session_state.tables[0].copy()

    # ============================================
    # FILTER OTOMATIS: buang Perubahan 0 / None / "-"
    # ============================================
    if "Perubahan" in df_selected.columns:
        ser = (
            df_selected["Perubahan"]
            .astype(str)
            .str.replace(",", "")
            .str.strip()
        )
        invalid_vals = ["0", "none", "-", "", "nan"]
        mask_valid = ~ser.str.lower().isin(invalid_vals)
        df_selected = df_selected[mask_valid]

    if df_selected.empty:
        st.warning(
            "Tidak ada data dengan nilai **Perubahan yang valid (≠ 0, None, '-')** "
            "pada semua halaman."
        )
        st.stop()

    # ===========================
    # FILTER BERDASARKAN 5 KOLOM
    # ===========================
    st.markdown("### 🔎 Filter Data (Jika Kolom Tersedia)")

    col_filters = {}
    with st.expander("Tampilkan opsi filter"):
        if "Kode Efek" in df_selected.columns:
            kode_opsi = sorted(df_selected["Kode Efek"].dropna().astype(str).unique())
            col_filters["Kode Efek"] = st.multiselect(
                "Filter Kode Efek",
                options=kode_opsi,
            )

        if "Nama Emiten" in df_selected.columns:
            col_filters["Nama Emiten"] = st.text_input("Filter Nama Emiten (contains)")

        if "Nama Pemegang Rekening Efek" in df_selected.columns:
            col_filters["Nama Pemegang Rekening Efek"] = st.text_input(
                "Filter Nama Pemegang Rekening Efek (contains)"
            )

        if "Nama Pemegang Saham" in df_selected.columns:
            col_filters["Nama Pemegang Saham"] = st.text_input(
                "Filter Nama Pemegang Saham (contains)"
            )

        if "Nama Rekening Efek" in df_selected.columns:
            col_filters["Nama Rekening Efek"] = st.text_input(
                "Filter Nama Rekening Efek (contains)"
            )

    df_view = df_selected.copy()

    # Filter Kode Efek
    if col_filters.get("Kode Efek"):
        df_view = df_view[
            df_view["Kode Efek"].astype(str).isin(col_filters["Kode Efek"])
        ]

    def apply_contains(df, col, value):
        if value and col in df.columns:
            return df[df[col].astype(str).str.contains(value, case=False, na=False)]
        return df

    df_view = apply_contains(df_view, "Nama Emiten", col_filters.get("Nama Emiten", ""))
    df_view = apply_contains(
        df_view,
        "Nama Pemegang Rekening Efek",
        col_filters.get("Nama Pemegang Rekening Efek", ""),
    )
    df_view = apply_contains(
        df_view,
        "Nama Pemegang Saham",
        col_filters.get("Nama Pemegang Saham", ""),
    )
    df_view = apply_contains(
        df_view,
        "Nama Rekening Efek",
        col_filters.get("Nama Rekening Efek", ""),
    )

    # 🔪 Hapus semua kolom SETELAH kolom "Perubahan"
    if "Perubahan" in df_view.columns:
        cols = list(df_view.columns)
        idx = cols.index("Perubahan")
        df_view = df_view.iloc[:, : idx + 1]

    st.write(f"Total baris setelah filter: **{len(df_view)}**")

    # ===========================
    # SIAPKAN DATAFRAME UNTUK TAMPILAN (MULTI-LEVEL HEADER)
    # ===========================
    df_display, perubahan_key = build_multilevel_header(df_view)

    # ===========================
    # Highlight Perubahan: hijau / merah
    # ===========================
    def highlight_perubahan(val):
        try:
            v = float(str(val).replace(",", "").replace(" ", ""))
        except Exception:
            return ""
        if v > 0:
            return "background-color: #c8f7c5;"  # hijau muda
        elif v < 0:
            return "background-color: #f8cccc;"  # merah muda
        else:
            return ""

    st.markdown("### Preview Tabel Terfilter")
    if perubahan_key is not None and perubahan_key in df_display.columns:
        styled = df_display.style.applymap(highlight_perubahan, subset=[perubahan_key])
        st.dataframe(styled, use_container_width=True)
    else:
        st.dataframe(df_display, use_container_width=True)

    # Download CSV hasil filter (pakai single-level header biar rapi, dan sudah dipotong sampai Perubahan)
    csv_buffer = io.StringIO()
    df_view.to_csv(csv_buffer, index=False)
    st.download_button(
        label="💾 Download CSV",
        data=csv_buffer.getvalue().encode("utf-8"),
        file_name="tabel_filtered_semua_halaman.csv",
        mime="text/csv",
    )

else:
    st.info("Belum ada tabel yang diekstrak. Silakan upload PDF dan klik **Ekstrak Tabel**.")

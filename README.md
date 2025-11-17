IDX Keterbukaan Informasi PDF Extractor
 ---------------------------------------------------------------
 Fitur utama:
 - Extract PDF IDX Keterbukaan Informasi 5% yang sudah didownload dari https://www.idx.co.id/id/perusahaan-tercatat/keterbukaan-informasi
 - App ini akan otomatis mengekstract tabel yang ada kemudian otomatis memfilter berdasarkan isi dalam kolom "Perubahan"
 - Tampilan ringkas (tabel) + detail per emiten
 - Ekspor hasil ke CSV

 ---------------------------------------------------------------
 Cara Menjalankan di lokal: 
  - pip3 install -r requirements.txt
  - streamlit run app.py

 Cara menjalankan di Ubuntu:
  - python3 -m venv .venv
  - source .venv/bin/activate
  - pip3 install streamlit pandas requests
  - streamlit run app.py

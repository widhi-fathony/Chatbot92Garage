# =============================================================================
# app.py — AI Chatbot Showroom "92 Car Garage" (VERSI GROQ API LATEST)
# =============================================================================

import os
import json
import re
import datetime
import pandas as pd
import streamlit as st
from groq import Groq
from dotenv import load_dotenv

# =============================================================================
# 1. KONFIGURASI AWAL - GROQ
# =============================================================================

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    st.error("❌ **GROQ_API_KEY tidak ditemukan!** Pastikan file `.env` sudah diisi dengan API Key dari Groq.")
    st.stop()

# Inisialisasi client Groq
client = Groq(api_key=GROQ_API_KEY)

# =============================================================================
# 2. KONSTANTA & KONFIGURASI SHOWROOM
# =============================================================================

EXCEL_FILE      = "DataStockMobil_92CarGarage_v2.xlsx"
SHEET_STOK      = "Data Stok Mobil"
SHEET_LEGENDA   = "Legenda & Panduan FAQ"

ADMIN_WA_NUMBER = "628113787077"  # ← GANTI dengan nomor WA Admin asli
ADMIN_WA_MESSAGE = "Halo Admin 92 Car Garage! Saya tertarik untuk survey fisik unit mobil. Mohon bantuannya 🙏"

# =============================================================================
# 3. FUNGSI BANTU — BACA EXCEL
# =============================================================================

@st.cache_data
def load_stock_data():
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_STOK, header=3)
        
        # JANGAN hapus kolom Unnamed dulu, kita ganti namanya secara manual jika ketemu link drive
        for col in df.columns:
            if "Unnamed" in str(col):
                # Mengecek apakah isi kolom tersebut mengandung link https://
                if df[col].astype(str).str.contains("https://").any():
                    df.rename(columns={col: "LINK FOTO MOBIL"}, inplace=True)
                    
        # Setelah diamankan, baru hapus kolom Unnamed sisanya
        df = df.loc[:, ~df.columns.str.contains("^Unnamed", case=False, na=False)]
        
        if "Nama Mobil" in df.columns:
            df = df.dropna(subset=["Nama Mobil"])
            
        df = df.reset_index(drop=True)
        return df, None
    except FileNotFoundError:
        return None, f"File `{EXCEL_FILE}` tidak ditemukan di folder."
    except Exception as e:
        return None, f"Gagal membaca file Excel: {e}"

@st.cache_data
def load_faq_legenda():
    try:
        df_faq = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_LEGENDA, header=None)
        lines = []
        for _, row in df_faq.iterrows():
            parts = [str(v) for v in row if pd.notna(v) and str(v).strip()]
            if parts:
                lines.append(" | ".join(parts))
        return "\n".join(lines)
    except Exception:
        return "Data FAQ tidak tersedia."

def format_stock_as_text(df):
    if df is None or df.empty:
        return "Tidak ada data stok mobil yang tersedia saat ini."
    lines = ["=== DATA STOK MOBIL 92 CAR GARAGE ===\n"]
    for _, row in df.iterrows():
        lines.append("--- UNIT ---")
        for col in df.columns:
            val = row[col]
            if pd.notna(val) and str(val).strip():
                lines.append(f"  {col}: {val}")
        lines.append("")
    return "\n".join(lines)

# =============================================================================
# 4. FUNGSI AI — LOGIKA CHATBOT
# =============================================================================

def classify_and_respond(user_message, chat_history, stock_context, faq_context, df_data):
    system_prompt = f"""
Kamu adalah Sales Assistant AI dari showroom mobil premium "92 Car Garage", 
berlokasi di Joglo, Jakarta Barat.

KARAKTER & GAYA KOMUNIKASI:
- Profesional, transparan, tapi tetap ramah dan kasual (anak muda gaul).
- Selalu sapa kustomer dengan "Kak" atau "Sahabat 92 Car Garage".
- Gunakan emoji secukupnya. Jangan berbohong/mengarang data!

DATA STOK MOBIL:
{stock_context}

PANDUAN FAQ:
{faq_context}

ATURAN KETAT (WAJIB DIPATUHI):
1. Kamu HANYA BOLEH membahas topik seputar mobil, otomotif, transaksi jual beli, dan layanan 92 Car Garage.
2. Jika kustomer bertanya DI LUAR TOPIK, KAMU WAJIB MENOLAK. Contoh: "Maaf Kak, aku cuma AI Sales Assistant yang ngerti soal mobil aja nih hehe 😅. Yuk bahas stok yang ready!"
3. ANTI HALUSINASI: JANGAN PERNAH mengarang, menebak, atau menyebutkan spesifikasi yang tidak tertulis di DATA STOK MOBIL.
4. ATURAN HARGA MOBIL: Di dalam data stok saat ini TIDAK ADA informasi harga. Jika kustomer bertanya soal harga atau simulasi kredit, JANGAN MENEBAK ANGKA APAPUN. Sampaikan dengan ramah bahwa harga spesial/nego bisa didiskusikan langsung dengan Admin, dan arahkan mereka untuk menekan tombol WhatsApp.

KLASIFIKASI INTENT:
- "serious_buyer": Tanya harga, minta simulasi kredit, minta survey fisik, nego serius, atau minta WA admin. (PENTING: Pertanyaan HARGA wajib masuk kategori ini).
- "general_question": Pertanyaan umum tentang ketersediaan stok, kondisi, pajak, dll.
- "other": Di luar topik otomotif/showroom.

OUTPUT HARUS DALAM FORMAT JSON BERIKUT:
{{"intent": "serious_buyer" | "general_question" | "other", "reply": "teks balasan kamu"}}
"""

    messages = [{"role": "system", "content": system_prompt}]
    
    # DIET TOKEN: Hanya mengirim 4 riwayat obrolan terakhir untuk menghemat token API
    for msg in chat_history[-4:]:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
        
    messages.append({"role": "user", "content": user_message})

    try:
        chat_completion = client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=1024,
            response_format={"type": "json_object"}
        )

        raw_text = chat_completion.choices[0].message.content
        parsed = json.loads(raw_text)

        intent      = parsed.get("intent", "general_question")
        reply_text  = parsed.get("reply", "Maaf, aku tidak bisa menjawab saat ini.")
        show_wa_btn = (intent == "serious_buyer")

        # --- LOGIKA BARU: MENCARI LINK FOTO MOBIL ---
        link_gambar = None
        if df_data is not None:
            for _, row in df_data.iterrows():
                # Jika "Nama Mobil" disebut dalam jawaban AI, ambil link gambarnya
                if pd.notna(row.get('Nama Mobil')) and str(row.get('Nama Mobil')) in reply_text:
                    val_link = row.get('LINK FOTO MOBIL')
                    if pd.notna(val_link) and str(val_link).strip():
                        link_gambar = str(val_link).strip()
                        break

        return {"reply": reply_text, "intent": intent, "show_wa_btn": show_wa_btn, "link_gambar": link_gambar}

    except Exception as e:
        return {"reply": f"⚠️ Terjadi kesalahan: {e}", "intent": "error", "show_wa_btn": False, "link_gambar": None}

# =============================================================================
# 5. FUNGSI AI — ADMIN PANEL
# =============================================================================

def analyze_customer_character(chat_history):
    if not chat_history:
        return "Belum ada percakapan."
    
    chat_text = "\n".join([f"[{'KUSTOMER' if m['role'] == 'user' else 'AI'}]: {m['content']}" for m in chat_history])
    prompt = f"Analisis percakapan showroom mobil berikut:\n\n{chat_text}\n\nBerikan profil kustomer, insight utama, potensi keberatan, dan draft pesan follow-up WA untuk admin dalam bahasa Indonesia yang rapi."
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile", # UPDATE: Model terbaru untuk analisis mendalam
            temperature=0.4
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Gagal menganalisis: {e}"

def extract_transactions_from_text(free_text):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    prompt = f"""
Ekstrak teks transaksi berikut ke format JSON Array.
TEKS: "{free_text}"

ATURAN:
1. Tanggal gunakan hari ini ({today_str}) jika tidak disebut.
2. Jenis harus "Pengeluaran" atau "Pemasukan".
3. Nominal berupa angka (integer) tanpa titik/koma.

OUTPUT HARUS JSON ARRAY SEPERTI INI:
[{{"Tanggal": "YYYY-MM-DD", "Jenis": "Pengeluaran", "Deskripsi": "contoh", "Nominal": 100000}}]
"""
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile", # UPDATE: Model terbaru untuk ekstraksi JSON
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        raw_text = chat_completion.choices[0].message.content
        parsed = json.loads(raw_text)
        
        for key in parsed:
            if isinstance(parsed[key], list):
                return parsed[key]
        return [parsed] if isinstance(parsed, dict) else None
        
    except Exception:
        return None

# =============================================================================
# 6. UI STREAMLIT
# =============================================================================

st.set_page_config(page_title="92 Car Garage — AI Chatbot", page_icon="🚗", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    :root { --accent: #305CDE; }
    h1 { color: var(--accent) !important; }
    .stLinkButton a { background-color: #25D366 !important; color: white !important; font-weight: bold !important; }
</style>
""", unsafe_allow_html=True)

df_stock, stock_error = load_stock_data()
faq_text = load_faq_legenda()
stock_context_text = format_stock_as_text(df_stock)

# --- KONFIGURASI SIDEBAR & MENU NAVIGASI ---
with st.sidebar:
    st.image("Screenshot 2026-06-23 225501.png", width=150)
    st.markdown("## 🚗 92 Car Garage")
    st.markdown(f"**WhatsApp Admin:** [Hubungi Kami](https://wa.me/{ADMIN_WA_NUMBER})")    
    st.divider()
    # FITUR BARU: MENU NAVIGASI
    pilihan_menu = st.radio("Pilih Halaman:", ["💬 Customer Mode", "📊 Admin Panel"])
    
    st.divider()
    if st.button("🔄 Reset Percakapan", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# --- JUDUL UTAMA ---
st.title("🚗 92 Car Garage — Chatbot Assistant")

if stock_error:
    st.warning(f"⚠️ {stock_error}")

# =============================================================================
# LOGIKA TAMPILAN BERDASARKAN MENU
# =============================================================================

# -----------------------------------------------------------------------------
# HALAMAN 1: KUSTOMER MODE (HANYA CHATBOT)
# -----------------------------------------------------------------------------
if pilihan_menu == "💬 Customer Mode":
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [{"role": "assistant", "content": "Halo Kak! Mau tanya soal unit mobil? Gas tanya aja ya! 😊"}]
    if "show_wa_button" not in st.session_state:
        st.session_state.show_wa_button = False

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state.show_wa_button:
        wa_link = f"https://wa.me/{ADMIN_WA_NUMBER}?text={ADMIN_WA_MESSAGE.replace(' ', '%20')}"
        st.link_button("📱 Chat Admin via WhatsApp", wa_link, use_container_width=True)

    user_input = st.chat_input("Tanya soal stok, kondisi mobil, dll...")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Mengetik..."):
                result = classify_and_respond(user_input, st.session_state.chat_history[:-1], stock_context_text, faq_text, df_stock)
            
            st.markdown(result["reply"])
            
            # --- FITUR BARU: MUNCULKAN GAMBAR DI CHAT ---
            if result.get("link_gambar"):
                st.image(result["link_gambar"], width=300, caption="Foto Unit")
                
            if result["show_wa_btn"]:
                st.session_state.show_wa_button = True
                wa_link = f"https://wa.me/{ADMIN_WA_NUMBER}?text={ADMIN_WA_MESSAGE.replace(' ', '%20')}"
                st.link_button("📱 Chat Admin via WhatsApp", wa_link, use_container_width=True)

        st.session_state.chat_history.append({"role": "assistant", "content": result["reply"]})

# -----------------------------------------------------------------------------
# HALAMAN 2: ADMIN PANEL (TABEL STOK & KONTROL TRANSAKSI)
# -----------------------------------------------------------------------------
elif pilihan_menu == "📊 Admin Panel":
    
    # 1. TABEL STOK PINDAH KE SINI
    if df_stock is not None:
        st.markdown("### 📋 Tabel Database Stok Mobil")
        # UPDATE: st.dataframe diubah jadi st.data_editor agar gambar muncul sebagai thumbnail
        st.data_editor(
            df_stock, 
            column_config={
                "LINK FOTO MOBIL": st.column_config.ImageColumn(
                    "Foto Unit",
                    help="Preview foto mobil",
                    width="medium" 
                )
            },
            use_container_width=True, 
            hide_index=True
        )
        st.divider()

    # 2. FITUR ADMIN PANEL
    st.header("📊 Admin Panel Control")
    st.subheader("🔍 Analisis Karakter Kustomer")
    
    chat_data = st.session_state.get("chat_history", [])
    cust_msgs = [m for m in chat_data if m["role"] == "user"]
    
    if cust_msgs:
        if st.button("🧠 Analisis Percakapan AI", type="primary"):
            with st.spinner("Menganalisis..."):
                hasil = analyze_customer_character(chat_data)
                st.markdown(hasil)
    else:
        st.info("Belum ada chat kustomer.")

    st.divider()
    st.subheader("💰 Pencatatan Transaksi (AI)")
    free_text_input = st.text_area("📝 Ketik pengeluaran/pemasukan bebas:")
    
    if st.button("⚡ Ekstrak Transaksi"):
        if free_text_input.strip():
            with st.spinner("Mengekstrak..."):
                ext = extract_transactions_from_text(free_text_input)
                if ext:
                    new_df = pd.DataFrame(ext)
                    if "transactions_df" not in st.session_state:
                        st.session_state.transactions_df = new_df
                    else:
                        st.session_state.transactions_df = pd.concat([st.session_state.transactions_df, new_df], ignore_index=True)
                    st.success("✅ Berhasil diekstrak!")
                else:
                    st.error("Gagal mengekstrak teks.")

    if "transactions_df" in st.session_state:
        edited_df = st.data_editor(st.session_state.transactions_df, num_rows="dynamic", key="editor")
        st.session_state.transactions_df = edited_df

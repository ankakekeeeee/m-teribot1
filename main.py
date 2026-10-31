import logging
import sqlite3
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Loglama ayarları
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- VERİTABANI İŞLEMLERİ ---
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    
    # Grup bilgileri tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            teminat REAL DEFAULT 1000.0,
            komisyon_orani REAL DEFAULT 10.0
        )
    """)
    
    # İşlem geçmişi tablosu (24 saatlik toplam gelen parayı hesaplamak için)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            amount REAL,
            timestamp INTEGER
        )
    """)
    
    conn.commit()
    conn.close()

def get_group_profile(chat_id):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT teminat, komisyon_orani FROM groups WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO groups (chat_id, teminat, komisyon_orani) VALUES (?, ?, ?)", (chat_id, 1000.0, 10.0))
        conn.commit()
        profile = {"teminat": 1000.0, "komisyon_orani": 10.0}
    else:
        profile = {"teminat": row[0], "komisyon_orani": row[1]}
        
    conn.close()
    return profile

def update_group_profile(chat_id, teminat=None, komisyon_orani=None):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    if teminat is not None:
        cursor.execute("UPDATE groups SET teminat = ? WHERE chat_id = ?", (teminat, chat_id))
    if komisyon_orani is not None:
        cursor.execute("UPDATE groups SET komisyon_orani = ? WHERE chat_id = ?", (komisyon_orani, chat_id))
    conn.commit()
    conn.close()

def log_trade(chat_id, amount):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    now = int(time.time())
    cursor.execute("INSERT INTO trade_logs (chat_id, amount, timestamp) VALUES (?, ?, ?)", (chat_id, amount, now))
    conn.commit()
    conn.close()

def get_24h_total_incoming(chat_id):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    # Son 24 saat (24 * 60 * 60 = 86400 saniye)
    day_ago = int(time.time()) - 86400
    
    cursor.execute("SELECT SUM(amount) FROM trade_logs WHERE chat_id = ? AND amount > 0 AND timestamp >= ?", (chat_id, day_ago))
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row and row[0] is not None else 0.0

# --- BOT KOMUTLARI VE MESAJLARI ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    profile = get_group_profile(chat_id)
    total_gelen = get_24h_total_incoming(chat_id)
    
    text = (
        f"🤖 **Profesör 47 - Teminat & Komisyon Takip Botu**\n\n"
        f"💰 Mevcut Teminat: `{profile['teminat']:,.2f}$`\n"
        f"📊 Komisyon Oranı: `%{profile['komisyon_orani']:.0f}`\n"
        f"📥 Son 24s Total Gelen: `{total_gelen:,.2f}$`\n\n"
        f"📌 **Komutlar:**\n"
        f"• `/teminat_ekle <miktar>` - Teminat ekler\n"
        f"• `/oran <yüzde>` - Komisyon oranını değiştirir\n"
        f"• `/bakiye` - Güncel durumu gösterir"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def bakiye_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    profile = get_group_profile(chat_id)
    total_gelen = get_24h_total_incoming(chat_id)
    
    text = (
        f"📊 **Güncel Durum Bilgisi**\n\n"
        f"💰 Kalan Teminat: `{profile['teminat']:,.2f}$`\n"
        f"✂️ Komisyon Oranı: `%{profile['komisyon_orani']:.0f}`\n"
        f"📥 Son 24s Total Gelen: `{total_gelen:,.2f}$`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def teminat_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    profile = get_group_profile(chat_id)
    
    if not context.args:
        await update.message.reply_text("⚠️ Lütfen eklenecek miktarı yazın. Örn: `/teminat_ekle 1000`", parse_mode="Markdown")
        return
    
    try:
        eklenen = float(context.args[0])
        yeni_teminat = profile["teminat"] + eklenen
        update_group_profile(chat_id, teminat=yeni_teminat)
        
        await update.message.reply_text(
            f"✅ **Teminat Başarıyla Eklendi!**\n\n"
            f"➕ Eklenen Miktar: `{eklenen:,.2f}$`\n"
            f"💰 **Yeni Kalan Tem:** `{yeni_teminat:,.2f}$`",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Geçersiz miktar girdiniz.")

async def oran_ayarla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    profile = get_group_profile(chat_id)
    
    if not context.args:
        await update.message.reply_text(f"📊 Mevcut oran: `%{profile['komisyon_orani']:.0f}`\nDeğiştirmek için: `/oran 10`", parse_mode="Markdown")
        return
    
    try:
        yeni_oran = float(context.args[0])
        update_group_profile(chat_id, komisyon_orani=yeni_oran)
        await update.message.reply_text(f"✅ Komisyon oranı başarıyla **%{yeni_oran:.0f}** olarak güncellendi.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Geçersiz oran girdiniz.")

async def handle_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
        
    chat_id = update.effective_chat.id
    profile = get_group_profile(chat_id)
    msg_text = update.message.text.strip().lower()

    is_positive = True
    if msg_text.startswith("+"):
        msg_text = msg_text[1:]
    elif msg_text.startswith("-"):
        is_positive = False
        msg_text = msg_text[1:]
    else:
        return 

    if msg_text.endswith("k"):
        try:
            val = float(msg_text[:-1]) * 1000
        except ValueError:
            return
    else:
        try:
            val = float(msg_text)
        except ValueError:
            return

    if not is_positive:
        val = -val

    if val > 0:
        gelen_para = val
        # İşlemi veritabanına logla (24 saatlik toplam için)
        log_trade(chat_id, gelen_para)
        
        komisyon_orani = profile["komisyon_orani"] / 100.0
        kesilen_komisyon = gelen_para * komisyon_orani
        teminden_dusen = gelen_para - kesilen_komisyon
        
        yeni_teminat = profile["teminat"] - teminden_dusen
        update_group_profile(chat_id, teminat=yeni_teminat)
        
        # Son 24 saatlik toplam geleni hesapla
        total_gelen = get_24h_total_incoming(chat_id)
        
        yanit = (
            f"📈 **İşlem İşlendi (+{val/1000:.0f}k)**\n\n"
            f"📥 Gelen Para: `{gelen_para:,.2f}$`\n"
            f"✂️ Kesilen Komisyon (%{profile['komisyon_orani']:.0f}): `{kesilen_komisyon:,.2f}$` (Sizin Kazancınız)\n"
            f"📉 Teminattan Düşen: `{teminden_dusen:,.2f}$`\n"
            f"💰 **Kalan Tem: {yeni_teminat:,.2f}$**\n"
            f"📊 **Total Gelen (24s): {total_gelen:,.2f}$**"
        )
    else:
        kayip = abs(val)
        yeni_teminat = profile["teminat"] - kayip
        update_group_profile(chat_id, teminat=yeni_teminat)
        
        total_gelen = get_24h_total_incoming(chat_id)
        
        yanit = (
            f"🔻 **Kayıp İşlendi (-{kayip/1000:.0f}k)**\n\n"
            f"📉 Kayıp Miktarı: `{kayip:,.2f}$`\n"
            f"💰 **Kalan Tem: {yeni_teminat:,.2f}$**\n"
            f"📊 **Total Gelen (24s): {total_gelen:,.2f}$**"
        )

    await update.message.reply_text(yanit, parse_mode="Markdown")

if __name__ == "__main__":
    TOKEN = "9126712433:AAHTEwxuLKAx-P8ds_wxTdKHB3CUhzgU5Xw"
    
    init_db()
    
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bakiye", bakiye_goster))
    app.add_handler(CommandHandler("teminat_ekle", teminat_ekle))
    app.add_handler(CommandHandler("oran", oran_ayarla))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_trade))

    print("Bot başarıyla başlatıldı ve çalışıyor...")
    app.run_polling()

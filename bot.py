import os
import logging
import asyncio
import tempfile
import shutil
import sqlite3
import argparse
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

# Global Değişkenler
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DOWNLOAD_DIR = tempfile.mkdtemp()
MAX_FILE_SIZE = 100  # Normal kullanıcılar için MB
PREMIUM_MAX_SIZE = 1024  # Premium kullanıcılar için MB
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")  # FFmpeg yolu

# Loglama Ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Veritabanı Bağlantısı
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()

# Dil Yapılandırması
LOCALES = {
    'tr': {
        'welcome': "👋 Hoş Geldiniz! Lütfen dil seçin:",
        'main_menu': "🌟 Ana Menü",
        'twitter_button': "🐦 Twitter Video İndir",
        'instagram_button': "📸 Instagram Video İndir",
        'help_button': "❓ Yardım ve İletişim",
        'premium_button': "💎 Premium Satın Al",
        'history_button': "📚 İndirme Geçmişi",
        'back_button': "🔙 Geri",
        'insta_prompt': "📥 Lütfen indirmek istediğiniz Instagram Reels/Video linkini gönderin:",
        'processing': "⏳ Video işleniyor...",
        'uploading': "📤 Video yükleniyor...\n\n❌ Hata: Timed out hatası alırsanız önemsemeyiniz, videonuz inecektir. Biraz bekleyiniz... ⏳",
        'help_message': "📞 İletişim Bilgilerim:\n\n"
                        "📸 Instagram: [Yasin](https://www.instagram.com/yasinnd67/)\n"
                        "🐦 Twitter: [Yasin](https://x.com/y739w)\n"
                        "📱 Telegram: [Yasin](https://t.me/yasinwegner)\n"
                        "📞 Telefon: +44 7441 944048"
    },
    'en': {
        'welcome': "👋 Welcome! Please choose language:",
        'main_menu': "🌟 Main Menu",
        'twitter_button': "🐦 Download Twitter Video",
        'instagram_button': "📸 Download Instagram Video",
        'help_button': "❓ Help & Contact",
        'premium_button': "💎 Buy Premium",
        'history_button': "📚 Download History",
        'back_button': "🔙 Back",
        'insta_prompt': "📥 Please send the Instagram Reels/Video link you want to download:",
        'processing': "⏳ Processing video...",
        'uploading': "📤 Uploading video...\n\n❌ Error: If you get a 'Timed out' error, don't worry, your video will be downloaded. Please wait... ⏳",
        'help_message': "📞 Contact Information:\n\n"
                        "📸 Instagram: [Yasin](https://www.instagram.com/yasinnd67/)\n"
                        "🐦 Twitter: [Yasin](https://x.com/y739w)\n"
                        "📱 Telegram: [Yasin](https://t.me/yasinwegner)\n"
                        "📞 Phone: +44 7441 944048"
    }
}

def get_locale(user_id):
    cursor.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 'tr'

def get_user_data(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def main_menu_keyboard(user_id):
    locale = get_locale(user_id)
    keyboard = [
        [InlineKeyboardButton(LOCALES[locale]['twitter_button'], callback_data='twitter')],
        [InlineKeyboardButton(LOCALES[locale]['instagram_button'], callback_data='instagram')],
        [
            InlineKeyboardButton(LOCALES[locale]['premium_button'], callback_data='premium'),
            InlineKeyboardButton(LOCALES[locale]['history_button'], callback_data='history')
        ],
        [InlineKeyboardButton(LOCALES[locale]['help_button'], callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button(user_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton(LOCALES[get_locale(user_id)]['back_button'], callback_data='main_menu')]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_user_data(user_id):
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    
    keyboard = [
        [InlineKeyboardButton("🇹🇷 Türkçe", callback_data='lang_tr'),
         InlineKeyboardButton("🇺🇸 English", callback_data='lang_en')]
    ]
    await update.message.reply_text(
        LOCALES['tr']['welcome'],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = context.user_data
    url = update.message.text.strip()
    
    if user_data.get('expecting_url'):
        platform = user_data['expecting_url']
        del user_data['expecting_url']
        
        try:
            temp_dir = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
            locale = get_locale(user_id)
            
            # FFmpeg entegrasyonu için kritik ayar
            cmd = [
                'yt-dlp',
                '-f', 'bestvideo+bestaudio/best',
                '-o', f'{temp_dir}/%(title)s.%(ext)s',
                '--ffmpeg-location', FFMPEG_PATH,  # FFmpeg path zorunlu
                '--merge-output-format', 'mp4',
                '--postprocessor-args', '-c:v libx264 -preset fast -crf 23',  # Codec fix
                '--socket-timeout', '30',
                '--retries', '3',
                url
            ]
            
            progress_msg = await update.message.reply_text(LOCALES[locale]['processing'])
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.communicate()
            
            downloaded_files = [f for f in os.listdir(temp_dir) if f.endswith('.mp4')]
            if not downloaded_files:
                raise Exception("Video bulunamadı")
            
            video_path = os.path.join(temp_dir, downloaded_files[0])
            file_size = os.path.getsize(video_path) / (1024 ** 2)
            
            user = get_user_data(user_id)
            max_size = PREMIUM_MAX_SIZE if user[2] else MAX_FILE_SIZE
            if file_size > max_size:
                raise Exception(f"Video boyutu limiti aşıyor ({max_size}MB)")
            
            cursor.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id=?", (user_id,))
            cursor.execute("INSERT INTO history (user_id, url, date) VALUES (?, ?, ?)", 
                          (user_id, url, datetime.now()))
            conn.commit()
            
            await progress_msg.edit_text(LOCALES[locale]['uploading'])
            with open(video_path, 'rb') as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption="🎉 İndirme başarılı!",
                    reply_markup=back_button(user_id)
                )
            
            shutil.rmtree(temp_dir)
            await progress_msg.delete()
            
        except Exception as e:
            logger.error(f"Hata: {str(e)}")
            await update.message.reply_text(
                f"❌ Hata: {str(e)}",
                reply_markup=back_button(user_id)
            )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    if query.data.startswith('lang_'):
        lang = query.data.split('_')[1]
        cursor.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
        conn.commit()
        await show_main_menu(query, lang)
        
    elif query.data == 'main_menu':
        await show_main_menu(query, get_locale(user_id))
        
    elif query.data == 'twitter':
        context.user_data['expecting_url'] = 'twitter'
        locale = get_locale(user_id)
        await query.edit_message_text(
            "🔗 Twitter/X video linkini gönderin:",
            reply_markup=back_button(user_id)
        )
    
    elif query.data == 'instagram':
        context.user_data['expecting_url'] = 'instagram'
        locale = get_locale(user_id)
        await query.edit_message_text(
            LOCALES[locale]['insta_prompt'],
            reply_markup=back_button(user_id)
        )
    
    elif query.data == 'premium':
        await query.edit_message_text(
            "💎 Premium Paket Özellikleri:\n\n"
            "✅ 1GB'a kadar video indirme\n"
            "🚀 Öncelikli Destek\n"
            "📈 Detaylı İstatistikler\n\n"
            "Fiyat: Aylık 49.99 TL",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Satın Al", callback_data='buy_premium')],
                [InlineKeyboardButton("🔙 Geri", callback_data='main_menu')]
            ])
        )
    
    elif query.data == 'history':
        cursor.execute("SELECT * FROM history WHERE user_id=? ORDER BY date DESC LIMIT 10", (user_id,))
        history = cursor.fetchall()
        text = "📚 Son 10 İndirme:\n\n"
        for item in history:
            text += f"📅 {item[3]} - {item[2]}\n"
        await query.edit_message_text(text, reply_markup=back_button(user_id))
    
    elif query.data == 'help':
        locale = get_locale(user_id)
        await query.edit_message_text(
            LOCALES[locale]['help_message'],
            reply_markup=back_button(user_id),
            parse_mode="Markdown"
        )

async def show_main_menu(query, lang):
    try:
        await query.edit_message_text(
            text=LOCALES[lang]['main_menu'],
            reply_markup=main_menu_keyboard(query.from_user.id)
        )
    except Exception as e:
        logger.error(f"Menü güncelleme hatası: {str(e)}")
        await query.message.reply_text(
            LOCALES[lang]['main_menu'],
            reply_markup=main_menu_keyboard(query.from_user.id)
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--init-db', action='store_true', help='Initialize database')
    args = parser.parse_args()
    
    if args.init_db:
        print("🔄 Veritabanı oluşturuluyor...")
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                        (user_id INTEGER PRIMARY KEY, 
                         language TEXT DEFAULT 'tr',
                         premium INTEGER DEFAULT 0,
                         downloads INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS history
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER,
                         url TEXT,
                         date TIMESTAMP)''')
        conn.commit()
        print("✅ Veritabanı başarıyla oluşturuldu!")
        conn.close()
        return

    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot başlatılıyor...")
    application.run_polling()
    conn.close()

if __name__ == '__main__':
    main()
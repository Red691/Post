import logging
import json
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes, PicklePersistence
)
from config import Config
from database import db

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
(TEMPLATE_NAME, TEMPLATE_LINK, TEMPLATE_MEDIA, TEMPLATE_CAPTION, 
 TEMPLATE_BUTTON_TEXT, TEMPLATE_BUTTON_URL, TEMPLATE_BUTTON_CONFIRM,
 POST_ANIME, POST_LINK, POST_MEDIA_SELECT, POST_PREVIEW,
 CHANNEL_FORWARD, BULK_POST) = range(13)

# Keyboards
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Template", callback_data="add_template"),
         InlineKeyboardButton("📋 My Templates", callback_data="list_templates")],
        [InlineKeyboardButton("📝 Create Post", callback_data="create_post"),
         InlineKeyboardButton("📢 My Channels", callback_data="list_channels")],
        [InlineKeyboardButton("⚙️ Auto Mode", callback_data="auto_mode"),
         InlineKeyboardButton("📤 Export/Import", callback_data="export_import")]
    ])

def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    await update.message.reply_text(
        "🎌 *Anime Template Poster Bot*\n\n"
        "Create reusable templates and generate posts instantly!",
        reply_markup=main_menu(),
        parse_mode='Markdown'
    )

# ==================== TEMPLATE CREATION ====================

async def add_template_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Step 1/5: Send the *Anime Name* (placeholder: `{anime}`)",
        reply_markup=cancel_keyboard(),
        parse_mode='Markdown'
    )
    return TEMPLATE_NAME

async def template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_template'] = {'anime_name': update.message.text}
    await update.message.reply_text(
        "Step 2/5: Send the *Default Link* (placeholder: `{link}`)",
        reply_markup=cancel_keyboard(),
        parse_mode='Markdown'
    )
    return TEMPLATE_LINK

async def template_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Invalid URL. Please send a valid link:")
        return TEMPLATE_LINK
    
    context.user_data['temp_template']['default_link'] = url
    await update.message.reply_text(
        "Step 3/5: Send the *Default Image or Video* (placeholder: `{media}`)",
        reply_markup=cancel_keyboard()
    )
    return TEMPLATE_MEDIA

async def template_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        media_type = 'photo'
    elif update.message.video:
        file_id = update.message.video.file_id
        media_type = 'video'
    else:
        await update.message.reply_text("❌ Please send an image or video.")
        return TEMPLATE_MEDIA
    
    context.user_data['temp_template']['media'] = file_id
    context.user_data['temp_template']['media_type'] = media_type
    
    default_caption = "🔥 {anime}\n\nWatch now 👇\n{link}"
    await update.message.reply_text(
        f"Step 4/5: Send the *Caption*\n\nDefault:\n`{default_caption}`\n\n"
        "Send custom text or click 'Use Default'",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Use Default", callback_data="default_caption")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]),
        parse_mode='Markdown'
    )
    return TEMPLATE_CAPTION

async def template_caption_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    default_caption = "🔥 {anime}\n\nWatch now 👇\n{link}"
    context.user_data['temp_template']['caption'] = default_caption
    context.user_data['temp_template']['buttons'] = []
    
    await query.edit_message_text(
        "Step 5/5: Setup Inline Buttons\n\n"
        "Current buttons: 0\n"
        "Button format: Text + URL (supports `{link}` placeholder)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Button", callback_data="add_button")],
            [InlineKeyboardButton("✅ Finish", callback_data="finish_buttons")]
        ])
    )
    return TEMPLATE_BUTTON_TEXT

async def template_caption_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_template']['caption'] = update.message.text
    context.user_data['temp_template']['buttons'] = []
    
    await update.message.reply_text(
        "Step 5/5: Setup Inline Buttons\n\n"
        "Current buttons: 0",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Button", callback_data="add_button")],
            [InlineKeyboardButton("✅ Finish", callback_data="finish_buttons")]
        ])
    )
    return TEMPLATE_BUTTON_TEXT

async def add_button_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Send button *text*:\nExample: `Watch Now`",
        reply_markup=cancel_keyboard(),
        parse_mode='Markdown'
    )
    return TEMPLATE_BUTTON_TEXT

async def button_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'current_button' not in context.user_data:
        context.user_data['current_button'] = {}
    context.user_data['current_button']['text'] = update.message.text
    
    await update.message.reply_text(
        "Send button *URL*:\nSupports: `{link}` for dynamic link",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Use Default {link}", callback_data="use_default_link")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]),
        parse_mode='Markdown'
    )
    return TEMPLATE_BUTTON_URL

async def button_url_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith(('http://', 'https://', '{link}')):
        await update.message.reply_text("❌ Invalid URL. Try again:")
        return TEMPLATE_BUTTON_URL
    
    context.user_data['current_button']['url'] = url
    
    keyboard = [[InlineKeyboardButton(
        context.user_data['current_button']['text'], 
        url=context.user_data['current_button']['url']
    )]]
    
    await update.message.reply_text(
        "Button preview:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text(
        "Add more buttons?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Another", callback_data="add_button"),
             InlineKeyboardButton("✅ Done", callback_data="confirm_button")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
    )
    return TEMPLATE_BUTTON_CONFIRM

async def use_default_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_button']['url'] = '{link}'
    
    keyboard = [[InlineKeyboardButton(
        context.user_data['current_button']['text'], 
        url="https://example.com"
    )]]
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Button preview (URL will be dynamic):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await query.message.reply_text(
        "Add more buttons?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Another", callback_data="add_button"),
             InlineKeyboardButton("✅ Done", callback_data="confirm_button")]
        ])
    )
    return TEMPLATE_BUTTON_CONFIRM

async def confirm_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if 'buttons' not in context.user_data['temp_template']:
        context.user_data['temp_template']['buttons'] = []
    
    context.user_data['temp_template']['buttons'].append([context.user_data['current_button']])
    context.user_data.pop('current_button', None)
    
    buttons_count = len(context.user_data['temp_template']['buttons'])
    await query.edit_message_text(
        f"Buttons: {buttons_count}\nSetup complete?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Button", callback_data="add_button"),
             InlineKeyboardButton("✅ Save Template", callback_data="save_template")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
    )
    return TEMPLATE_BUTTON_CONFIRM

async def save_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    template = context.user_data['temp_template']
    template['name'] = template.get('anime_name', 'Untitled')
    
    template_id = db.add_template(user_id, template)
    
    await query.edit_message_text(
        f"✅ Template saved!\n\n"
        f"*Name:* {template['name']}\n"
        f"*Caption:* {template['caption'][:50]}...\n"
        f"*Buttons:* {len(template['buttons'])}",
        reply_markup=main_menu(),
        parse_mode='Markdown'
    )
    context.user_data.clear()
    return ConversationHandler.END

# ==================== LIST & MANAGE TEMPLATES ====================

async def list_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = db.get_user(update.effective_user.id)
    templates = user.get('templates', [])
    
    if not templates:
        await query.edit_message_text(
            "No templates yet!\nCreate one first.",
            reply_markup=main_menu()
        )
        return
    
    keyboard = []
    for idx, template in enumerate(templates, 1):
        keyboard.append([InlineKeyboardButton(
            f"{idx}. {template['name']}", 
            callback_data=f"view_template:{template['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_menu")])
    
    await query.edit_message_text(
        f"📋 Your Templates ({len(templates)}):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def view_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    template_id = query.data.split(":")[1]
    user = db.get_user(update.effective_user.id)
    
    template = next((t for t in user['templates'] if t['id'] == template_id), None)
    if not template:
        await query.edit_message_text("Template not found!", reply_markup=main_menu())
        return
    
    context.user_data['viewing_template'] = template
    
    keyboard = [
        [InlineKeyboardButton("📝 Edit", callback_data=f"edit_template:{template_id}"),
         InlineKeyboardButton("🗑 Delete", callback_data=f"delete_template:{template_id}")],
        [InlineKeyboardButton("📋 Duplicate", callback_data=f"dup_template:{template_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="list_templates")]
    ]
    
    await query.edit_message_text(
        f"🎨 *Template:* {template['name']}\n\n"
        f"*Caption:*\n{template['caption']}\n\n"
        f"*Buttons:* {len(template['buttons'])}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def delete_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    template_id = query.data.split(":")[1]
    db.delete_template(update.effective_user.id, template_id)
    
    await query.edit_message_text(
        "🗑 Template deleted!",
        reply_markup=main_menu()
    )

async def duplicate_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    template_id = query.data.split(":")[1]
    user = db.get_user(update.effective_user.id)
    template = next((t for t in user['templates'] if t['id'] == template_id), None)
    
    if template:
        new_template = template.copy()
        new_template['name'] = f"{template['name']} (Copy)"
        db.add_template(update.effective_user.id, new_template)
        await query.edit_message_text(
            "📋 Template duplicated!",
            reply_markup=main_menu()
        )

# ==================== POST CREATION ====================

async def create_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = db.get_user(update.effective_user.id)
    if not user.get('templates'):
        await query.edit_message_text(
            "No templates! Create one first.",
            reply_markup=main_menu()
        )
        return
    
    await query.edit_message_text(
        "📝 *Create New Post*\n\nSend the *Anime Name*:",
        reply_markup=cancel_keyboard(),
        parse_mode='Markdown'
    )
    return POST_ANIME

async def post_anime_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['post_anime'] = update.message.text
    await update.message.reply_text(
        "Send the *Link* (URL):",
        reply_markup=cancel_keyboard(),
        parse_mode='Markdown'
    )
    return POST_LINK

async def post_link_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Invalid URL. Try again:")
        return POST_LINK
    
    context.user_data['post_link'] = url
    
    await update.message.reply_text(
        "Send *Image or Video* (optional - press Skip to use template default):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭ Skip", callback_data="skip_media")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
    )
    return POST_MEDIA_SELECT

async def post_media_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['post_media'] = update.message.photo[-1].file_id
        context.user_data['post_media_type'] = 'photo'
    elif update.message.video:
        context.user_data['post_media'] = update.message.video.file_id
        context.user_data['post_media_type'] = 'video'
    else:
        await update.message.reply_text("❌ Send image or video:")
        return POST_MEDIA_SELECT
    
    return await show_template_selection(update, context)

async def skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['post_media'] = None
    return await show_template_selection(update, context, query=query)

async def show_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    user = db.get_user(update.effective_user.id)
    templates = user['templates']
    
    keyboard = []
    for template in templates:
        keyboard.append([InlineKeyboardButton(
            template['name'], 
            callback_data=f"select_template:{template['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    
    text = "Select *Template* to use:"
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return POST_PREVIEW

async def generate_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    template_id = query.data.split(":")[1]
    user = db.get_user(update.effective_user.id)
    template = next((t for t in user['templates'] if t['id'] == template_id), None)
    
    if not template:
        await query.edit_message_text("Error: Template not found")
        return ConversationHandler.END
    
    # Replace placeholders
    anime = context.user_data['post_anime']
    link = context.user_data['post_link']
    media = context.user_data.get('post_media') or template['media']
    media_type = context.user_data.get('post_media_type') or template.get('media_type', 'photo')
    
    caption = template['caption'].replace('{anime}', anime).replace('{link}', link)
    
    # Process buttons
    keyboard = []
    for row in template['buttons']:
        new_row = []
        for btn in row:
            btn_url = btn['url'].replace('{link}', link)
            new_row.append(InlineKeyboardButton(btn['text'], url=btn_url))
        keyboard.append(new_row)
    
    # Add action buttons
    keyboard.append([
        InlineKeyboardButton("✅ Send to Channel", callback_data=f"send_channel:{template_id}"),
        InlineKeyboardButton("💬 Send Here", callback_data=f"send_here:{template_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("✏️ Edit Caption", callback_data=f"edit_cap:{template_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")
    ])
    
    context.user_data['current_post'] = {
        'template_id': template_id,
        'caption': caption,
        'media': media,
        'media_type': media_type,
        'keyboard': keyboard[:-2]  # Without action buttons
    }
    
    # Send preview
    markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if media_type == 'photo':
            await query.message.reply_photo(media, caption=caption, reply_markup=markup, parse_mode='Markdown')
        else:
            await query.message.reply_video(media, caption=caption, reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        await query.edit_message_text(f"Error: {str(e)}\n\nTry another template.")
        return ConversationHandler.END
    
    await query.message.delete()
    return ConversationHandler.END

async def send_post_here(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    post = context.user_data.get('current_post')
    if not post:
        await query.edit_message_text("Session expired!")
        return
    
    try:
        if post['media_type'] == 'photo':
            await query.message.reply_photo(post['media'], caption=post['caption'], 
                                          reply_markup=InlineKeyboardMarkup(post['keyboard']),
                                          parse_mode='Markdown')
        else:
            await query.message.reply_video(post['media'], caption=post['caption'], 
                                          reply_markup=InlineKeyboardMarkup(post['keyboard']),
                                          parse_mode='Markdown')
        await query.message.delete()
    except Exception as e:
        await query.edit_message_text(f"Error: {str(e)}")

# ==================== CHANNEL MANAGEMENT ====================

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = db.get_user(update.effective_user.id)
    channels = user.get('channels', [])
    
    keyboard = []
    for ch in channels:
        name = ch.get('title') or ch.get('username') or str(ch['id'])
        keyboard.append([InlineKeyboardButton(f"📢 {name}", callback_data=f"ch_post:{ch['id']}")])
    
    keyboard.append([
        InlineKeyboardButton("➕ Add Channel", callback_data="add_channel"),
        InlineKeyboardButton("🗑 Manage", callback_data="manage_channels")
    ])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_menu")])
    
    await query.edit_message_text(
        f"📢 Your Channels ({len(channels)}):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Forward a message from your channel or send the channel username (@channel)\n\n"
        "*Note:* Bot must be admin in the channel with post permissions.",
        reply_markup=cancel_keyboard(),
        parse_mode='Markdown'
    )
    return CHANNEL_FORWARD

async def channel_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = None
    channel_title = None
    username = None
    
    if update.message.forward_from_chat:
        channel_id = update.message.forward_from_chat.id
        channel_title = update.message.forward_from_chat.title
        username = update.message.forward_from_chat.username
    elif update.message.text and update.message.text.startswith('@'):
        username = update.message.text
        # Try to get chat info (requires bot to be member)
        try:
            chat = await context.bot.get_chat(username)
            channel_id = chat.id
            channel_title = chat.title
        except:
            await update.message.reply_text(
                "❌ Cannot access channel. Make sure:\n"
                "1. Bot is added to channel\n"
                "2. Bot has admin rights\n"
                "3. Try forwarding a message instead",
                reply_markup=main_menu()
            )
            return ConversationHandler.END
    
    if not channel_id:
        await update.message.reply_text("❌ Invalid input. Forward message or send @username:")
        return CHANNEL_FORWARD
    
    # Check permissions
    try:

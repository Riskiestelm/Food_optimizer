import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from dishes import suggest_dish, suggest_both
from cooldown import mark_cooked, get_recent_history

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ── Keyboards ────────────────────────────────────────────────────────────────

def meal_selection_keyboard(action: str) -> InlineKeyboardMarkup:
    """Keyboard to pick a meal slot. action = 'veg' | 'nonveg' | 'both'"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌅 Breakfast", callback_data=f"{action}|breakfast"),
            InlineKeyboardButton("☀️ Lunch",     callback_data=f"{action}|lunch"),
            InlineKeyboardButton("🌙 Dinner",    callback_data=f"{action}|dinner"),
        ]
    ])


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🥦 Suggest Veg",     callback_data="pick|veg"),
            InlineKeyboardButton("🍗 Suggest Non-Veg", callback_data="pick|nonveg"),
        ],
        [
            InlineKeyboardButton("🍽️ Suggest Both",   callback_data="pick|both"),
        ],
        [
            InlineKeyboardButton("📋 History",         callback_data="history"),
        ],
    ])


# ── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Food Optimizer*\n\nWhat do you want to do?",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Step 1: user picks veg / non-veg / both → ask which meal ──
    if data.startswith("pick|"):
        action = data.split("|")[1]
        label = {"veg": "Veg", "nonveg": "Non-Veg", "both": "Both"}[action]
        await query.edit_message_text(
            f"*{label}* — pick a meal slot:",
            parse_mode="Markdown",
            reply_markup=meal_selection_keyboard(action),
        )

    # ── Step 2: user picks meal slot → show suggestion ──
    elif "|" in data and data.split("|")[0] in ("veg", "nonveg", "both"):
        action, meal = data.split("|")

        if action == "both":
            result = suggest_both(meal)
            veg     = result["veg"]
            nonveg  = result["non-veg"]

            lines = [f"*{meal.capitalize()} suggestions:*\n"]
            keyboard_rows = []

            if veg:
                lines.append(f"🥦 *Veg:* {veg['name']}")
                keyboard_rows.append([InlineKeyboardButton(
                    f"✅ Mark '{veg['name']}' as cooked",
                    callback_data=f"cooked|{veg['name']}"
                )])
            else:
                lines.append("🥦 *Veg:* No dishes available (all on cooldown)")

            if nonveg:
                lines.append(f"🍗 *Non-Veg:* {nonveg['name']}")
                keyboard_rows.append([InlineKeyboardButton(
                    f"✅ Mark '{nonveg['name']}' as cooked",
                    callback_data=f"cooked|{nonveg['name']}"
                )])
            else:
                lines.append("🍗 *Non-Veg:* No dishes available (all on cooldown)")

            keyboard_rows.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
            await query.edit_message_text(
                "\n".join(lines),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard_rows),
            )

        else:
            dtype = "veg" if action == "veg" else "non-veg"
            dish = suggest_dish(dtype, meal)
            emoji = "🥦" if dtype == "veg" else "🍗"

            if dish:
                await query.edit_message_text(
                    f"*{meal.capitalize()} suggestion:*\n\n{emoji} {dish['name']}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            f"✅ Mark as cooked",
                            callback_data=f"cooked|{dish['name']}"
                        )],
                        [InlineKeyboardButton("🔙 Back", callback_data="back")],
                    ]),
                )
            else:
                await query.edit_message_text(
                    f"😕 No {dtype} dishes available for *{meal}* — all are on cooldown.\n\nTry again tomorrow or add more dishes to your sheet.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data="back")]
                    ]),
                )

    # ── Mark as cooked ──
    elif data.startswith("cooked|"):
        dish_name = data.split("|", 1)[1]
        mark_cooked(dish_name)
        await query.edit_message_text(
            f"✅ *{dish_name}* marked as cooked!\n\nIt won't appear in suggestions for 3 days.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Main Menu", callback_data="back")]
            ]),
        )

    # ── History ──
    elif data == "history":
        history = get_recent_history(limit=10)
        if not history:
            text = "📋 *History*\n\nNo dishes cooked yet."
        else:
            lines = ["📋 *Recent dishes:*\n"]
            for entry in history:
                lines.append(f"• *{entry['dish']}* — cooked {entry['cooked_on']}\n  _{entry['status']}_")
            text = "\n".join(lines)

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back")]
            ]),
        )

    # ── Back to main menu ──
    elif data == "back":
        await query.edit_message_text(
            "👋 *Food Optimizer*\n\nWhat do you want to do?",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

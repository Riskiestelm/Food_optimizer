import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dishes import get_available_dishes
from cooldown import mark_cooked, get_recent_history

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# ── Keyboards ────────────────────────────────────────────────────────────────

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🥦 Veg",     callback_data="pick|veg"),
            InlineKeyboardButton("🍗 Non-Veg", callback_data="pick|nonveg"),
        ],
        [
            InlineKeyboardButton("🍽️ Both",   callback_data="pick|both"),
        ],
        [
            InlineKeyboardButton("📋 History", callback_data="history"),
        ],
    ])


def meal_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌅 Breakfast", callback_data=f"{action}|breakfast"),
            InlineKeyboardButton("☀️ Lunch",     callback_data=f"{action}|lunch"),
            InlineKeyboardButton("🌙 Dinner",    callback_data=f"{action}|dinner"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="back")],
    ])


# ── Helpers ──────────────────────────────────────────────────────────────────

def build_dish_list_message(dtype: str, meal: str) -> tuple[str, list[dict]]:
    """
    Build a numbered list message for available dishes.
    Returns (message_text, dishes_list).
    dishes_list is empty if all are on cooldown.
    """
    emoji = "🥦" if dtype == "veg" else "🍗"
    label = "Veg" if dtype == "veg" else "Non-Veg"
    dishes = get_available_dishes(dtype, meal)

    if not dishes:
        text = (
            f"{emoji} *{label} — {meal.capitalize()}*\n\n"
            f"No dishes available — everything is on cooldown."
        )
        return text, []

    lines = [f"{emoji} *{label} — {meal.capitalize()}*\n\nReply with a number to mark as cooked:\n"]
    for i, dish in enumerate(dishes, start=1):
        lines.append(f"{i}. {dish['name']}")

    return "\n".join(lines), dishes


# ── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 *Food Optimizer*\n\nWhat do you want to do?",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Step 1: pick category → ask meal slot
    if data.startswith("pick|"):
        action = data.split("|")[1]
        label = {"veg": "Veg", "nonveg": "Non-Veg", "both": "Both"}[action]
        await query.edit_message_text(
            f"*{label}* — pick a meal slot:",
            parse_mode="Markdown",
            reply_markup=meal_keyboard(action),
        )

    # Step 2: pick meal slot → show numbered list
    elif "|" in data and data.split("|")[0] in ("veg", "nonveg", "both"):
        action, meal = data.split("|")
        context.user_data.clear()

        if action == "both":
            # Send veg list
            veg_text, veg_dishes = build_dish_list_message("veg", meal)
            nonveg_text, nonveg_dishes = build_dish_list_message("non-veg", meal)

            # Store both lists; prefix determines which list a number maps to
            # veg: indices 1..len(veg), non-veg: indices len(veg)+1..total
            context.user_data["pending_both"] = {
                "veg": veg_dishes,
                "nonveg": nonveg_dishes,
                "meal": meal,
            }

            combined_lines = [f"🍽️ *Both — {meal.capitalize()}*\n"]

            if veg_dishes:
                combined_lines.append("🥦 *Veg:*")
                for i, dish in enumerate(veg_dishes, start=1):
                    combined_lines.append(f"  {i}. {dish['name']}")
            else:
                combined_lines.append("🥦 *Veg:* No dishes available — everything is on cooldown.")

            offset = len(veg_dishes)
            if nonveg_dishes:
                combined_lines.append("\n🍗 *Non-Veg:*")
                for i, dish in enumerate(nonveg_dishes, start=offset + 1):
                    combined_lines.append(f"  {i}. {dish['name']}")
            else:
                combined_lines.append("\n🍗 *Non-Veg:* No dishes available — everything is on cooldown.")

            if veg_dishes or nonveg_dishes:
                combined_lines.append("\nReply with a number to mark as cooked.")

            await query.edit_message_text(
                "\n".join(combined_lines),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="back")]
                ]),
            )

        else:
            dtype = "veg" if action == "veg" else "non-veg"
            text, dishes = build_dish_list_message(dtype, meal)

            if dishes:
                context.user_data["pending"] = {"dishes": dishes, "dtype": dtype}

            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="back")]
                ]),
            )

    # History
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

    # Back to main menu
    elif data == "back":
        context.user_data.clear()
        await query.edit_message_text(
            "👋 *Food Optimizer*\n\nWhat do you want to do?",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )


async def number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain-text number replies to pick a dish from the list."""
    text = update.message.text.strip()

    if not text.isdigit():
        return  # ignore non-numeric messages

    choice = int(text)

    # ── Both mode ──
    if "pending_both" in context.user_data:
        data = context.user_data["pending_both"]
        veg_dishes = data["veg"]
        nonveg_dishes = data["nonveg"]
        offset = len(veg_dishes)
        total = offset + len(nonveg_dishes)

        if choice < 1 or choice > total:
            await update.message.reply_text(f"Please send a number between 1 and {total}.")
            return

        if choice <= offset:
            dish = veg_dishes[choice - 1]
        else:
            dish = nonveg_dishes[choice - offset - 1]

        mark_cooked(dish["name"])
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ *{dish['name']}* marked as cooked! It won't appear for 3 days.",
            parse_mode="Markdown",
        )

    # ── Single category mode ──
    elif "pending" in context.user_data:
        dishes = context.user_data["pending"]["dishes"]
        total = len(dishes)

        if choice < 1 or choice > total:
            await update.message.reply_text(f"Please send a number between 1 and {total}.")
            return

        dish = dishes[choice - 1]
        mark_cooked(dish["name"])
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ *{dish['name']}* marked as cooked! It won't appear for 3 days.",
            parse_mode="Markdown",
        )

    # No active list
    else:
        await update.message.reply_text(
            "No active dish list. Use /start to begin.",
        )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, number_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

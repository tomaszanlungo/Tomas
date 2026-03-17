import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from config import TELEGRAM_TOKEN
from ai_handler import classify_message, classify_message_from_audio
from sheets_handler import (
    append_expense, update_last_expense, get_last_row_number, write_summary_to_sheet
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Memoria en tiempo de ejecución: user_id → número de fila del último gasto guardado
_last_row: dict[int, int] = {}


async def _handle_result(update: Update, result: dict, user_id: int) -> None:
    """Procesa el resultado clasificado por la IA y actúa según el intent."""
    intent = result.get("intent")

    if intent == "add":
        expenses = result.get("expenses", [])
        if not expenses:
            await update.message.reply_text(
                "No encontré ningún gasto en tu mensaje. "
                "Intenta con algo como: 'Almuerzo 1500 débito' o 'Uber 800 y café 200 efectivo'."
            )
            return

        saved = []
        last_row = None
        for expense in expenses:
            try:
                last_row = append_expense(
                    date=expense["fecha"],
                    description=expense["descripcion"],
                    amount=expense["monto"],
                    category=expense["categoria"],
                    payment_method=expense["metodo_pago"],
                )
                saved.append(
                    f"✓ {expense['descripcion']} — ${expense['monto']} "
                    f"({expense['categoria']}, {expense['metodo_pago']}, {expense['fecha']})"
                )
            except Exception as e:
                saved.append(f"✗ {expense['descripcion']}: error al guardar ({e})")

        if last_row:
            _last_row[user_id] = last_row

        await update.message.reply_text("Gastos registrados:\n" + "\n".join(saved))

    elif intent == "edit":
        fields = result.get("fields", {})
        if not fields:
            await update.message.reply_text(
                "Entendí que querés editar, pero no detecté qué cambiar. "
                "Intenta ser más específico, por ejemplo: 'el monto era 1500' o 'fue con débito'."
            )
            return

        # Usa la fila en memoria; si no hay (bot reiniciado), lee la última de Sheets
        row = _last_row.get(user_id) or get_last_row_number()

        try:
            update_last_expense(fields, row_number=row)
            changes = ", ".join(
                f"{k}: {v}" for k, v in fields.items()
            )
            await update.message.reply_text(f"Último gasto actualizado (fila {row}):\n{changes}")
        except Exception as e:
            await update.message.reply_text(f"Error al actualizar el gasto: {e}")

    elif intent == "query":
        from datetime import date as _date
        month = result.get("month") or _date.today().month
        year  = result.get("year")  or _date.today().year

        try:
            summary = write_summary_to_sheet(month, year)
        except Exception as e:
            await update.message.reply_text(f"Error al generar el resumen: {e}")
            return

        if summary["count"] == 0:
            await update.message.reply_text(
                f"No encontré gastos para {summary['month_name']} {year}."
            )
            return

        lines = [f"📊 *Resumen de {summary['month_name']} {year}*\n"]
        for cat, total in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: ${total:,.0f}")
        lines.append(f"\n💰 *Total: ${summary['total']:,.0f}*")
        lines.append(f"_({summary['count']} gastos registrados)_")
        lines.append("\n_La pestaña 'Resumen' en Sheets fue actualizada._")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    else:
        await update.message.reply_text("No entendí tu mensaje. Intentá de nuevo.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Procesando...")
    try:
        result = classify_message(update.message.text)
    except Exception as e:
        await update.message.reply_text(f"No pude interpretar el mensaje. Error: {e}")
        return
    await _handle_result(update, result, update.effective_user.id)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Transcribiendo audio...")

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    audio_path = f"temp_voice_{update.message.message_id}.ogg"
    await file.download_to_drive(audio_path)

    try:
        result = classify_message_from_audio(audio_path)
    except Exception as e:
        await update.message.reply_text(f"No pude procesar el audio. Error: {e}")
        return
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

    await _handle_result(update, result, update.effective_user.id)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    logging.info("Bot iniciado. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()

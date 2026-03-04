from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand


async def set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Приветственное сообщение"),
        BotCommand(command="search", description="Поиск: /search #тег или /search ключевое_слово"),
        BotCommand(command="stats", description="Статистика бота"),
        BotCommand(command="retry", description="Повторить обработку: /retry или /retry <id>"),
        BotCommand(command="digest", description="Запустить агрегатор вручную"),
    ]
    await bot.set_my_commands(commands)

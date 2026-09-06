import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = False  # sadece slash komutları kullanıyoruz, gerek yok

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f" Giriş yapıldı: {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f" {len(synced)} slash komutu senkronize edildi.")
    except Exception as e:
        print(f"Senkronizasyon hatası: {e}")


async def main():
    async with bot:
        await bot.load_extension("cogs.career_cog")
        await bot.start(TOKEN)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_BOT_TOKEN bulunamadı. Lütfen .env dosyasına token'ını ekle."
        )
    asyncio.run(main())
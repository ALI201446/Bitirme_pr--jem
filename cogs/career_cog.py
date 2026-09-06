import json
import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

import storage
from ai_advisor import get_ai_recommendation, get_followup_answer

CAREERS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "careers.json")

with open(CAREERS_PATH, "r", encoding="utf-8") as f:
    CAREERS = json.load(f)

# Yaş/seviye grubuna göre farklı soru setleri.
QUESTIONS_LISE = [
    "Okulda en çok hangi derslerde kendini iyi hissediyorsun, en çok hangilerinden sıkılıyorsun?",
    "Boş zamanında (oyun, sosyal medya, spor, çizim vb.) yapmaktan en çok keyif aldığın şey nedir?",
    "Ders çalışırken tek başına mı, yoksa arkadaşlarınla birlikte mi daha verimli oluyorsun?",
    "Büyüyünce nasıl bir hayatın olsun istersin — seyahat eden mi, sabit bir yerde mi, ofiste mi dışarıda mı çalışan biri?",
    "Bir problemle karşılaştığında (ödev, arkadaş sorunu, teknik bir arıza vb.) genelde nasıl yaklaşırsın?",
    "Ailende veya çevrende hayran olduğun bir meslek sahibi var mı, varsa neyi beğeniyorsun?",
    "Elinle bir şeyler yapmayı (yapım, tamir, çizim, enstrüman vb.) mi yoksa ekranda/kağıtta fikir üretmeyi mi seversin?",
    "Üniversitede ya da hayatta hangi konuda uzmanlaşmayı hayal ediyorsun?",
]

QUESTIONS_YETISKIN = [
    "Şu anki (veya en son) işinde/okulunda seni en çok tatmin eden şey ne oldu?",
    "Tek başına mı çalışmayı, yoksa bir ekiple mi çalışmayı tercih edersin? Neden?",
    "Hangi konularda kendini güçlü hissediyorsun (örn. sayısal analiz, yaratıcılık, insan ilişkileri, teknik problem çözme)?",
    "Hayalindeki bir iş gününü tarif eder misin — nasıl bir ortamda, ne yaparken mutlu olurdun?",
    "Bir problemle karşılaştığında genelde nasıl yaklaşırsın?",
    "Kariyerinde seni en çok ne motive ediyor: yüksek gelir, anlamlı iş, esneklik, statü, yaratıcılık, yoksa istikrar mı?",
    "Elinle bir şeyler üretmeyi mi (yapım, tamir, sanat vb.) yoksa fikir/strateji üzerinde çalışmayı mı tercih edersin?",
    "5 yıl sonra kendini nasıl bir hayatta/işte hayal ediyorsun?",
]

TIMEOUT_SECONDS = 180
FOLLOWUP_TIMEOUT_SECONDS = 120


class LevelSelectView(discord.ui.View):
    """Kullanıcının yaş/seviye grubunu seçmesi için buton menüsü."""

    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.selected: str | None = None
        self.event = asyncio.Event()

    async def _handle(self, interaction: discord.Interaction, choice: str, label: str):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Bu senin akışın değil! Kendi keşfini başlatmak için `/kariyer-kesfet` yazabilirsin.",
                ephemeral=True,
            )
            return
        self.selected = choice
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ {label} seçildi. Sorular geliyor...", view=self
        )
        self.event.set()

    @discord.ui.button(label="🎓 Lise Öğrencisi", style=discord.ButtonStyle.primary)
    async def lise_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "lise", "Lise Öğrencisi")

    @discord.ui.button(label="💼 Üniversite / Yetişkin", style=discord.ButtonStyle.success)
    async def yetiskin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "yetiskin", "Üniversite / Yetişkin")

    @discord.ui.button(label="🐬 Biz Kimiz", style=discord.ButtonStyle.grey)
    async def about_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🐬 Dolphins Technologies",
            description="Kariyer keşfi yapan bu botun arkasındaki ekip ve şirket hakkında birkaç bilgi:",
            color=discord.Color.teal(),
        )
        embed.add_field(
            name="👨‍💻 Kurucu",
            value="**Dozdar** — Dolphins Technologies'in kurucusu ve yazılımcısı. Bu botu da baştan sona kendisi geliştirdi.",
            inline=False,
        )
        embed.add_field(
            name="🏢 Şirket",
            value="Dolphins Technologies, yapay zeka destekli ürünler ve eğlenceli dijital deneyimler geliştiren bir teknoloji şirketi.",
            inline=False,
        )
        embed.add_field(
            name="🤝 İş Birlikleri",
            value="Söylentilere göre Sony ile gizli bir Ar-Ge projesi yürütülüyormuş 👀 (şaka amaçlı eklenmiş bir easter egg'dir, gerçek değildir)",
            inline=False,
        )
        embed.set_footer(text="🐬 Dolphins Technologies — hayali bir şirkettir, eğlence amaçlıdır.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class FollowUpView(discord.ui.View):
    """Sonuç ekranına eklenen, kullanıcının önerilen meslekler hakkında
    yapay zekaya ek soru sorabilmesini sağlayan buton."""

    def __init__(self, bot: commands.Bot, user_id: int, channel_id: int, matched_careers, qa_pairs):
        super().__init__(timeout=600)
        self.bot = bot
        self.user_id = user_id
        self.channel_id = channel_id
        self.matched_careers = matched_careers
        self.qa_pairs = qa_pairs

    @discord.ui.button(label="💬 Bir meslek hakkında soru sor", style=discord.ButtonStyle.secondary)
    async def ask_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Bu senin sonucun değil! Kendi keşfini başlatmak için `/kariyer-kesfet` yazabilirsin.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✍️ Ne merak ediyorsun? Örnek: *\"Yazılım Geliştirici olmak için hangi bölümü okumalıyım?\"* "
            f"— cevabını bu kanala yaz ({FOLLOWUP_TIMEOUT_SECONDS} saniyen var)."
        )

        def check(m: discord.Message):
            return m.author.id == self.user_id and m.channel.id == self.channel_id

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=FOLLOWUP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            await interaction.channel.send("⏰ Süre doldu, tekrar sormak için butona basabilirsin.")
            return

        thinking = await interaction.channel.send(
            embed=discord.Embed(description="🧠 Yanıt hazırlanıyor...", color=discord.Color.blurple())
        )
        answer = await asyncio.to_thread(
            get_followup_answer, self.matched_careers, self.qa_pairs, msg.content
        )
        if not answer:
            await thinking.edit(
                embed=discord.Embed(
                    description="⚠️ Şu anda yanıt üretemedim, birazdan tekrar dener misin?",
                    color=discord.Color.red(),
                )
            )
            return
        await thinking.edit(
            embed=discord.Embed(title="🤖 Yanıt", description=answer, color=discord.Color.green())
        )


def find_career(name: str):
    """AI'nin döndürdüğü ismi careers.json'daki kayıtla eşleştirir (esnek eşleşme)."""
    name_norm = name.strip().lower()
    for c in CAREERS:
        if c["name"].strip().lower() == name_norm:
            return c
    # Tam eşleşme yoksa kısmi eşleşmeye bak
    for c in CAREERS:
        if name_norm in c["name"].strip().lower() or c["name"].strip().lower() in name_norm:
            return c
    return None


class CareerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="kariyer-kesfet", description="Sohbet ederek kariyer keşif sürecini başlat")
    async def kariyer_kesfet(self, interaction: discord.Interaction):
        user = interaction.user
        channel = interaction.channel

        level_view = LevelSelectView(user.id)
        await interaction.response.send_message(
            f"Merhaba {user.mention}! Önce sana uygun soruları hazırlayalım — hangi gruptasın?",
            view=level_view,
        )
        try:
            await asyncio.wait_for(level_view.event.wait(), timeout=60)
        except asyncio.TimeoutError:
            await channel.send(f"⏰ {user.mention}, süre doldu. Tekrar denemek için `/kariyer-kesfet` yazabilirsin.")
            return

        questions = QUESTIONS_LISE if level_view.selected == "lise" else QUESTIONS_YETISKIN

        intro = discord.Embed(
            title="🧭 Kariyer Keşfi",
            description=(
                "Sana birkaç soru soracağım, cevaplarını bu kanala yazman yeterli. "
                "Cevaplarına göre yapay zeka sana uygun meslekler önerecek.\n\n"
                f"Her soru için {TIMEOUT_SECONDS} saniyen var."
            ),
            color=discord.Color.blurple(),
        )
        await channel.send(embed=intro)

        def check(m: discord.Message):
            return m.author.id == user.id and m.channel.id == channel.id

        qa_pairs = []
        for i, question in enumerate(questions, start=1):
            q_embed = discord.Embed(
                title=f"Soru {i}/{len(questions)}",
                description=question,
                color=discord.Color.blurple(),
            )
            await channel.send(embed=q_embed)

            try:
                msg = await self.bot.wait_for(
                    "message", check=check, timeout=TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                await channel.send(
                    f"⏰ {user.mention}, süre doldu. Tekrar denemek için "
                    "`/kariyer-kesfet` yazabilirsin."
                )
                return

            qa_pairs.append((question, msg.content))

        thinking_msg = await channel.send(
            embed=discord.Embed(
                title="🧠 Cevapların analiz ediliyor...",
                description="Yapay zeka sana en uygun meslekleri belirliyor. Google'ın sunucuları yoğunsa birkaç kez tekrar denenebilir, bu normal — biraz sürebilir.",
                color=discord.Color.blurple(),
            )
        )

        result = await asyncio.to_thread(get_ai_recommendation, qa_pairs, CAREERS)

        if not result or not result.get("recommended"):
            await thinking_msg.edit(
                embed=discord.Embed(
                    title="⚠️ Bir sorun oluştu",
                    description=(
                        "Yapay zeka şu anda öneri üretemedi. Bu genelde `GEMINI_API_KEY` "
                        "eksik/hatalı olduğunda ya da API'ye ulaşılamadığında olur. "
                        "Lütfen daha sonra tekrar dene."
                    ),
                    color=discord.Color.red(),
                )
            )
            return

        matched_careers = []
        for name in result["recommended"]:
            career = find_career(name)
            if career:
                matched_careers.append((career, result.get("reasons", {}).get(name, "")))

        storage.save_profile(user.id, qa_pairs, [c["name"] for c, _ in matched_careers])

        embed = discord.Embed(
            title="✨ Senin İçin Önerilen Kariyerler",
            description="Cevaplarına göre yapay zekanın sana önerdiği meslekler:",
            color=discord.Color.green(),
        )
        for career, reason in matched_careers:
            value = f"{career['description']}\n**Gerekli beceriler:** {', '.join(career['skills'])}"
            if reason:
                value += f"\n💡 *{reason}*"
            embed.add_field(name=f"📌 {career['name']}", value=value, inline=False)

        if result.get("comment"):
            embed.add_field(name="🤖 Genel Yorum", value=result["comment"], inline=False)
        embed.set_footer(text="Tekrar denemek için /kariyer-kesfet yazabilirsin.")

        followup_view = FollowUpView(self.bot, user.id, channel.id, matched_careers, qa_pairs)
        await thinking_msg.edit(embed=embed, view=followup_view)

    @app_commands.command(name="kariyer-profilim", description="Daha önceki kariyer önerilerini gör")
    async def kariyer_profilim(self, interaction: discord.Interaction):
        profile = storage.get_profile(interaction.user.id)
        if not profile["history"]:
            await interaction.response.send_message(
                "Henüz bir kariyer keşfi yapmadın. `/kariyer-kesfet` ile başlayabilirsin!",
                ephemeral=True,
            )
            return

        last = profile["history"][-1]
        embed = discord.Embed(
            title="📂 Kariyer Profilin",
            description=f"Son önerilen kariyerler: {', '.join(last)}",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CareerCog(bot))
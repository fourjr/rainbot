import discord
from discord.ext import commands

from rainbot.main import RainBot
from ..ext.command import command, group


class AIModeration(commands.Cog):
    def __init__(self, bot: RainBot) -> None:
        self.bot = bot

    @group(5, invoke_without_command=True)
    async def aimoderation(self, ctx: commands.Context) -> None:
        """AI moderation management commands.

        Related commands:
        - aisensitivity - Adjust AI sensitivity level
        """
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="aimoderation")

    @aimoderation.command(name="enable")
    async def ai_enable(self, ctx: commands.Context, category: str = None) -> None:
        """Enable AI moderation for all categories or a specific category."""
        valid_categories = [
            "hate",
            "hate/threatening",
            "self-harm",
            "sexual",
            "sexual/minors",
            "violence",
            "violence/graphic",
        ]

        if category is None or category == "all":
            # Enable the main AI moderation
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {"detections.ai_moderation.enabled": True}}
            )
            # Enable all categories
            for cat in valid_categories:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"detections.ai_moderation.categories.{cat}": True}}
                )
            await ctx.send("✅ AI moderation **enabled** for all categories.")
        elif category in valid_categories:
            # Enable the main AI moderation if not already enabled
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {"detections.ai_moderation.enabled": True}}
            )
            # Enable the specific category
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {f"detections.ai_moderation.categories.{category}": True}}
            )
            await ctx.send(f"✅ AI moderation **enabled** for '{category}' category.")
        else:
            await ctx.send(
                f"❌ Invalid category. Valid categories: {', '.join(valid_categories)} or 'all'"
            )

    @aimoderation.command(name="disable")
    async def ai_disable(self, ctx: commands.Context, category: str = None) -> None:
        """Disable AI moderation for all categories or a specific category."""
        valid_categories = [
            "hate",
            "hate/threatening",
            "self-harm",
            "sexual",
            "sexual/minors",
            "violence",
            "violence/graphic",
        ]

        if category is None or category == "all":
            # Disable the main AI moderation and all categories
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {"detections.ai_moderation.enabled": False}}
            )
            for cat in valid_categories:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"detections.ai_moderation.categories.{cat}": False}}
                )
            await ctx.send("❌ AI moderation **disabled** for all categories.")
        elif category in valid_categories:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {f"detections.ai_moderation.categories.{category}": False}}
            )
            await ctx.send(f"❌ AI moderation **disabled** for '{category}' category.")
        else:
            await ctx.send(
                f"❌ Invalid category. Valid categories: {', '.join(valid_categories)} or 'all'"
            )

    @command(5, parent="aimoderation")
    async def aisensitivity(self, ctx: commands.Context, level: int = None) -> None:
        """Adjust the AI's sensitivity (0-100).

        Usage: aisensitivity <level>

        Sensitivity levels:
        • Lower % (0-30): Less strict - Only catches obvious violations
        • Medium % (40-70): Balanced - Catches most violations
        • Higher % (80-100): More strict - Catches subtle violations too

        Examples:
        • aisensitivity 20 - Very lenient, only extreme content
        • aisensitivity 50 - Balanced moderation
        • aisensitivity 90 - Strict, catches borderline content
        """
        if level is None:
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            current = guild_config.detections.ai_moderation.sensitivity
            await ctx.send(
                f"**Current AI sensitivity:** {current}%\n\n**Sensitivity Guide:**\n• **0-30%**: Less strict - Only obvious violations\n• **40-70%**: Balanced - Most violations\n• **80-100%**: More strict - Subtle violations too\n\n**Usage:** `aisensitivity <0-100>`"
            )
            return

        if not 0 <= level <= 100:
            await ctx.send("Sensitivity level must be between 0 and 100.")
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {"detections.ai_moderation.sensitivity": level}}
        )
        await ctx.send(f"AI moderation sensitivity set to {level}.")

    @aimoderation.command(name="category")
    async def ai_category(
        self, ctx: commands.Context, category: str = None, enabled: bool = None
    ) -> None:
        """Enable or disable specific AI moderation categories.

        Usage: aimoderation category [category] [true/false]
        Run without arguments to see available categories.
        """
        valid_categories = [
            "hate",
            "hate/threatening",
            "self-harm",
            "sexual",
            "sexual/minors",
            "violence",
            "violence/graphic",
        ]

        if category is None:
            await ctx.send(
                f"**Available AI moderation categories:**\n{chr(10).join(f'• {cat}' for cat in valid_categories)}\n\nUsage: `aimoderation category <category> <true/false>`\n\nExamples:\n`aimoderation category hate true` - Enable hate detection\n`aimoderation category violence false` - Disable violence detection"
            )
            return

        if category not in valid_categories:
            await ctx.send(f"Invalid category. Valid categories: {', '.join(valid_categories)}")
            return

        if enabled is None:
            await ctx.send(f"Please specify true or false for category '{category}'.")
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {f"detections.ai_moderation.categories.{category}": enabled}}
        )
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"AI moderation category '{category}' {status}.")

    @aimoderation.command(name="punishment")
    async def ai_punishment(self, ctx: commands.Context, action: str, value) -> None:
        """Configure AI moderation punishments."""
        valid_actions = ["warn", "mute", "kick", "ban", "delete"]

        if action not in valid_actions:
            await ctx.send(f"Invalid action. Valid actions: {', '.join(valid_actions)}")
            return

        if action == "delete":
            value = (
                bool(value)
                if isinstance(value, str) and value.lower() in ["true", "false"]
                else value
            )
        elif action == "warn":
            value = int(value) if str(value).isdigit() else 0
        elif action in ["kick", "ban"]:
            value = (
                bool(value)
                if isinstance(value, str) and value.lower() in ["true", "false"]
                else value
            )

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {f"detection_punishments.ai_moderation.{action}": value}}
        )
        await ctx.send(f"AI moderation {action} punishment set to {value}.")

    @aimoderation.command(name="config")
    async def ai_config(self, ctx: commands.Context) -> None:
        """View current AI moderation configuration."""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        ai_config = guild_config.detections.ai_moderation
        punishments = guild_config.detection_punishments.ai_moderation

        embed = discord.Embed(
            title="AI Moderation Configuration", color=0x00FF00 if ai_config.enabled else 0xFF0000
        )
        embed.add_field(
            name="Status", value="Enabled" if ai_config.enabled else "Disabled", inline=True
        )
        embed.add_field(name="Sensitivity", value=f"{ai_config.sensitivity}%", inline=True)

        categories = "\n".join(
            [f"{cat}: {'✅' if enabled else '❌'}" for cat, enabled in ai_config.categories.items()]
        )
        embed.add_field(name="Categories", value=categories, inline=False)

        punishment_text = "\n".join([f"{action}: {value}" for action, value in punishments.items()])
        embed.add_field(name="Punishments", value=punishment_text, inline=False)

        await ctx.send(embed=embed)

    @aimoderation.command(name="status")
    async def ai_status(self, ctx: commands.Context) -> None:
        """View current AI moderation status."""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        ai_config = guild_config.detections.ai_moderation
        punishments = guild_config.detection_punishments.ai_moderation

        enabled_categories = [k for k, v in ai_config.categories.items() if v]
        disabled_categories = [k for k, v in ai_config.categories.items() if not v]

        embed = discord.Embed(
            title="🤖 AI Moderation Status",
            color=discord.Color.green() if ai_config.enabled else discord.Color.red(),
        )

        embed.add_field(
            name="Status",
            value=f"{'🟢 Enabled' if ai_config.enabled else '🔴 Disabled'}",
            inline=True,
        )
        embed.add_field(name="Sensitivity", value=f"{ai_config.sensitivity}%", inline=True)

        if enabled_categories:
            embed.add_field(
                name="✅ Enabled Categories",
                value="\n".join([f"• {cat}" for cat in enabled_categories]),
                inline=False,
            )

        if disabled_categories:
            embed.add_field(
                name="❌ Disabled Categories",
                value="\n".join([f"• {cat}" for cat in disabled_categories]),
                inline=False,
            )

        punishment_text = "\n".join(
            [f"• {action}: {value}" for action, value in punishments.items() if value]
        )
        if punishment_text:
            embed.add_field(name="🛡️ Active Punishments", value=punishment_text, inline=False)

        await ctx.send(embed=embed)


async def setup(bot: RainBot) -> None:
    await bot.add_cog(AIModeration(bot))

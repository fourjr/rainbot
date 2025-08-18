import discord
from discord.ext import commands

from rainbot.main import RainBot
from ..ext.command import group


class AIModeration(commands.Cog):
    def __init__(self, bot: RainBot) -> None:
        self.bot = bot

    @group(6, invoke_without_command=True, aliases=["aimod"])
    async def aimoderation(self, ctx: commands.Context) -> None:
        """**AI-powered moderation tools**

        This command provides access to AI-powered moderation features.
        Use the subcommands to configure and use the AI moderation tools.

        **Subcommands:**
        - `toggle` - Enable or disable both text and image AI moderation.
        - `sensitivity` - Adjust the AI's sensitivity.
        - `punishment` - Set the punishment for AI moderation flags.
        - `categories` - Manage AI moderation categories.
        - `text` - Toggle text moderation only.
        - `image` - Toggle image moderation only.
        - `settings` - View the current AI moderation settings.
        - `help` - Show this help message.
        """
        pass  # Help is now handled automatically by RainGroup

    @aimoderation.command()
    async def toggle(self, ctx: commands.Context, state: bool = None) -> None:
        """Enable or disable both text and image AI moderation."""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if state is None:
            state = not guild_config.detections.ai_moderation.enabled
        await self.bot.db.update_guild_config(
            ctx.guild.id,
            {
                "$set": {
                    "detections.ai_moderation.enabled": state,
                    "detections.image_moderation.enabled": state,
                }
            },
        )
        await ctx.send(
            f"AI moderation (text and image) has been {'enabled' if state else 'disabled'}."
        )

    @aimoderation.command()
    async def sensitivity(self, ctx: commands.Context, level: int) -> None:
        """Adjust the AI's sensitivity."""
        if not 0 <= level <= 100:
            await ctx.send("Sensitivity level must be between 0 and 100.")
            return
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {"detections.ai_moderation.sensitivity": level}}
        )
        await ctx.send(f"AI moderation sensitivity set to {level}.")

    @aimoderation.command()
    async def punishment(
        self,
        ctx: commands.Context,
        action: str,
        value: str = None,
    ) -> None:
        """Set the punishment for AI moderation flags.

        **Usage:**
        - `aimoderation punishment <action> [value]`

        **Actions:**
        - `warn`: Warns the user. Requires a number for the warning.
        - `mute`: Mutes the user. Requires a duration for the mute.
        - `kick`: Kicks the user.
        - `ban`: Bans the user.
        - `delete`: Deletes the message.
        """
        action = action.lower()
        valid_actions = ["warn", "mute", "kick", "ban", "delete"]
        if action not in valid_actions:
            await ctx.send(f"Invalid action. Valid actions are: {', '.join(valid_actions)}")
            return

        if action in ["warn", "mute"] and value is None:
            await ctx.send(f"A value is required for the `{action}` action.")
            return

        update_key = f"detection_punishments.ai_moderation.{action}"
        update_value = None

        if action == "warn":
            update_value = int(value)
        elif action == "mute":
            update_value = value
        else:
            update_value = value.lower() == "true" if value is not None else True

        await self.bot.db.update_guild_config(ctx.guild.id, {"$set": {update_key: update_value}})
        await ctx.send(f"Punishment for {action} set to {update_value}.")

    @aimoderation.group(invoke_without_command=True)
    async def categories(
        self, ctx: commands.Context, category: str = None, state: bool = None
    ) -> None:
        """Enable, disable, or list AI moderation categories.

        **Usage:**
        - `aimoderation categories` - Lists all categories and their status.
        - `aimoderation categories <name> <true/false>` - Enables or disables a category.
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        all_categories = guild_config.detections.ai_moderation.categories

        if category is None:
            embed = discord.Embed(title="AI Moderation Categories", color=discord.Color.blue())
            category_text = "\n".join(
                [
                    f"`{cat}`: {'Enabled' if enabled else 'Disabled'}"
                    for cat, enabled in all_categories.items()
                ]
            )
            embed.description = category_text
            await ctx.send(embed=embed)
            return

        category = category.lower()
        if category not in all_categories:
            await ctx.send(
                f"Invalid category. Valid categories are: {', '.join(all_categories.keys())}"
            )
            return

        current_state = all_categories[category]
        if state is None:
            state = not current_state

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {f"detections.ai_moderation.categories.{category}": state}}
        )
        await ctx.send(f"Category `{category}` has been {'enabled' if state else 'disabled'}.")

    @aimoderation.command()
    async def text(self, ctx: commands.Context, state: bool = None) -> None:
        """Enable or disable AI text moderation only."""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if state is None:
            state = not guild_config.detections.ai_moderation.enabled
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {"detections.ai_moderation.enabled": state}}
        )
        await ctx.send(f"AI text moderation has been {'enabled' if state else 'disabled'}.")

    @aimoderation.command()
    async def image(self, ctx: commands.Context, state: bool = None) -> None:
        """Enable or disable AI image moderation only."""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if state is None:
            state = not guild_config.detections.image_moderation.enabled
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {"detections.image_moderation.enabled": state}}
        )
        await ctx.send(f"AI image moderation has been {'enabled' if state else 'disabled'}.")

    @aimoderation.command()
    async def settings(self, ctx: commands.Context) -> None:
        """View the current AI moderation settings."""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        settings = guild_config.detections.ai_moderation
        punishments = guild_config.detection_punishments.ai_moderation

        embed = discord.Embed(title="AI Moderation Settings", color=discord.Color.blue())
        embed.add_field(
            name="Text Moderation",
            value="Enabled" if settings.enabled else "Disabled",
            inline=False,
        )
        embed.add_field(
            name="Image Moderation",
            value="Enabled" if guild_config.detections.image_moderation.enabled else "Disabled",
            inline=False,
        )
        embed.add_field(name="Sensitivity", value=settings.sensitivity, inline=False)

        punishment_text = ""
        for action, value in punishments.items():
            punishment_text += f"**{action.capitalize()}**: {value}\n"
        embed.add_field(name="Punishments", value=punishment_text, inline=False)

        category_text = ""
        for category, enabled in settings.categories.items():
            category_text += f"`{category}`: {'Enabled' if enabled else 'Disabled'}\n"
        embed.add_field(name="Categories", value=category_text, inline=False)

        await ctx.send(embed=embed)

    @aimoderation.command(name="help")
    async def help_command(self, ctx: commands.Context) -> None:
        """Shows this help message."""
        await ctx.send_help(self.aimoderation)


async def setup(bot: RainBot) -> None:
    await bot.add_cog(AIModeration(bot))

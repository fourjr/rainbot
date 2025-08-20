"""
Custom help command for RainBot
"""

import discord
from discord.ext import commands
from collections import OrderedDict
from utils.helpers import create_embed
from core.permissions import PermissionLevel


class Help(commands.Cog):
    """
    📜 **Help Command**

    Provides detailed help on commands and categories.
    """

    def __init__(self, bot):
        self.bot = bot
        # Remove the default help command
        self.bot.remove_command("help")
        # Define the category structure
        self.categories = OrderedDict(
            [
                (
                    "🛡️ Moderation",
                    [
                        "aimoderation",
                        "ban",
                        "kick",
                        "lockdown",
                        "modlogs",
                        "mute",
                        "muted",
                        "note",
                        "purge",
                        "slowmode",
                        "softban",
                        "unban",
                        "unmute",
                        "warn",
                    ],
                ),
                (
                    "⚙️ Setup",
                    [
                        "automod",
                        "importconfig",
                        "resetconfig",
                        "setalert",
                        "setannouncement",
                        "setcommandlevel",
                        "setmuterole",
                        "setoffset",
                        "setpermission",
                        "setprefix",
                        "setwarnpunishment",
                        "setup",
                        "viewconfig",
                    ],
                ),
                (
                    "🎭 Roles",
                    [
                        "autorole",
                        "iam",
                        "iamnot",
                        "reactionrole",
                        "role",
                        "selfrole",
                    ],
                ),
                ("📝 Tags", ["addcommand", "canned", "tag"]),
                (
                    "🎉 Giveaways",
                    [
                        "giveaway",
                        "giveaway_edit_description",
                        "giveaway_edit_winners",
                        "giveaway_end",
                        "giveaway_reroll",
                        "giveaway_start",
                        "giveaway_stats",
                        "giveaway_stop",
                        "setgiveaway",
                    ],
                ),
                (
                    "📊 Utility",
                    [
                        "about",
                        "detections",
                        "eval",
                        "exportconfig",
                        "help",
                        "invite",
                        "load",
                        "logging",
                        "ping",
                        "reload",
                        "reminder",
                        "remindercancel",
                        "remindlist",
                        "server",
                        "serverhealth",
                        "stats",
                        "testperms",
                        "unload",
                        "user",
                    ],
                ),
            ]
        )

    async def get_filtered_commands(self, ctx):
        """Get a list of all commands the user can actually run."""
        filtered = {}
        # This is a bit slow, but necessary to get accurate command lists
        for cmd in self.bot.commands:
            try:
                if await cmd.can_run(ctx):
                    filtered[cmd.name] = cmd
                    for alias in cmd.aliases:
                        filtered[alias] = cmd
            except commands.CommandError:
                continue
        return filtered

    @commands.command(name="help", aliases=["h", "commands"])
    async def help_command(self, ctx, *, query: str = None):
        """Shows this message."""
        if not query:
            await self.send_main_help(ctx)
        else:
            await self.send_queried_help(ctx, query)

    async def send_main_help(self, ctx):
        """Sends the main help embed listing all categories."""
        embed = create_embed(
            title="RainBot Help",
            description=f"Use `{ctx.prefix}help <category>` to see the commands in that category.",
            color="info",
        )

        available_commands = await self.get_filtered_commands(ctx)

        for category_name, command_list in self.categories.items():
            # Only show commands that exist and the user can run
            valid_commands = [cmd for cmd in command_list if cmd in available_commands]
            if valid_commands:
                # Create a formatted string of commands for the category
                command_text = ", ".join(sorted([f"`{cmd}`" for cmd in valid_commands]))
                embed.add_field(
                    name=category_name,
                    value=command_text,
                    inline=False,  # Set to False to have commands listed under the category title
                )

        await ctx.send(embed=embed)

    async def send_queried_help(self, ctx, query):
        """Sends a more specific help embed for a category or command."""
        query_lower = query.lower()

        # Handle subcommands
        parts = query_lower.split()
        if len(parts) > 1:
            cmd = self.bot.get_command(query_lower)
            if cmd and cmd.name != "help":
                help_text = (cmd.help or "No description available.").format(
                    prefix=ctx.prefix
                )
                embed = create_embed(
                    title=f"{ctx.prefix}{cmd.qualified_name} {cmd.signature}",
                    description=help_text,
                    color="info",
                )
                if cmd.aliases:
                    embed.add_field(
                        name="Aliases",
                        value=", ".join(f"`{a}`" for a in cmd.aliases),
                        inline=False,
                    )
                if (
                    hasattr(cmd, "__original_kwargs__")
                    and "level" in cmd.__original_kwargs__
                ):
                    level = cmd.__original_kwargs__["level"]
                    perm_name = PermissionLevel(level).name.replace("_", " ").title()
                    embed.add_field(
                        name="Permissions", value=f"`{perm_name}`", inline=False
                    )
                await ctx.send(embed=embed)
                return

        available_commands = await self.get_filtered_commands(ctx)

        # Check if query is a category
        for category_name, command_list in self.categories.items():
            category_simple_name = category_name.split(" ")[1].lower()
            if query_lower == category_simple_name:

                valid_commands = [
                    cmd for cmd in command_list if cmd in available_commands
                ]

                if not valid_commands:
                    await ctx.send(
                        embed=create_embed(
                            title="No Commands",
                            description="You don't have permission to use any commands in this category.",
                            color="warning",
                        )
                    )
                    return

                embed = create_embed(title=category_name, color="info")
                command_text = ", ".join(sorted([f"`{cmd}`" for cmd in valid_commands]))
                embed.description = command_text
                await ctx.send(embed=embed)
                return

        # Check if query is a command
        if query_lower in available_commands:
            cmd = available_commands[query_lower]

            # Format the help string with the correct prefix
            help_text = (cmd.help or "No description available.").format(
                prefix=ctx.prefix
            )

            embed = create_embed(
                title=f"{ctx.prefix}{cmd.qualified_name} {cmd.signature}",
                description=help_text,
                color="info",
            )
            if cmd.aliases:
                embed.add_field(
                    name="Aliases",
                    value=", ".join(f"`{a}`" for a in cmd.aliases),
                    inline=False,
                )

            # Show required permission level
            if (
                hasattr(cmd, "__original_kwargs__")
                and "level" in cmd.__original_kwargs__
            ):
                level = cmd.__original_kwargs__["level"]
                perm_name = PermissionLevel(level).name.replace("_", " ").title()
                embed.add_field(
                    name="Permissions", value=f"`{perm_name}`", inline=False
                )
            elif hasattr(cmd, "all_commands"):  # For command groups
                # This is a bit more complex, we'll just show the parent's permission
                if (
                    hasattr(cmd, "__original_kwargs__")
                    and "level" in cmd.__original_kwargs__
                ):
                    level = cmd.__original_kwargs__["level"]
                    perm_name = PermissionLevel(level).name.replace("_", " ").title()
                    embed.add_field(
                        name="Permissions", value=f"`{perm_name}`", inline=False
                    )

            await ctx.send(embed=embed)
            return

        # Not found
        embed = create_embed(
            title="Not Found",
            description=f"Could not find a command or category named `{query}`.",
            color="error",
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))

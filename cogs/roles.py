import discord
from discord.ext import commands
from discord.ext.commands import Cog

from bot import rainbot
from ext.command import group, check_perm_level
from ext.utility import EmojiOrUnicode, tryint


async def selfrole_check(ctx: commands.Context) -> bool:
    selfroles = (await ctx.bot.db.get_guild_config(ctx.guild.id)).selfroles
    return bool(selfroles) or await check_perm_level(ctx, command_level=10)


class Roles(commands.Cog):
    """Set up roles that users can get"""

    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.order = 5

    @commands.check(selfrole_check)
    @group(0, invoke_without_command=True)
    async def selfrole(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """**Assign or remove a self-assignable role**

        This command allows you to give yourself an available self-role, or remove one you already have.

        **Usage:**
        `{prefix}selfrole <role_name>`

        **<role_name>:**
        The name of the role you want to add or remove.

        **Subcommands:**
        - `add` - (Admin) Add a role to the list of self-assignable roles.
        - `remove` - (Admin) Remove a role from the list.
        - `list` - View all available self-assignable roles.

        **Example:**
        `{prefix}selfrole Blue Team`
        """
        selfroles = (await self.bot.db.get_guild_config(ctx.guild.id)).selfroles
        if str(role.id) not in selfroles:
            await ctx.send(f"{role.name} is not an available selfrole.")
            return
        if role in ctx.author.roles:
            await ctx.author.remove_roles(role, reason="Selfrole")
            await ctx.send(f"Removed role {self.bot.accept}")
        else:
            await ctx.author.add_roles(role, reason="Selfrole")
            await ctx.send(f"Added role {self.bot.accept}")

    @selfrole.command(10)
    async def add(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """**Add a self-assignable role**

        This command makes a role available for users to assign to themselves.

        **Usage:**
        `{prefix}selfrole add <role>`

        **<role>:**
        - Mention the role, e.g., `@Blue Team`
        - Provide the role name, e.g., `Blue Team`
        - Provide the role ID.

        **Example:**
        `{prefix}selfrole add Blue Team`
        """
        if role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner.id:
            await ctx.send("User has insufficient permissions")
            return
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$addToSet": {"selfroles": str(role.id)}}
        )
        await ctx.send(f"Added {role.mention} as a selfrole.")

    @selfrole.command(10, aliases=["del", "delete"])
    async def remove(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """**Remove a self-assignable role**

        This command removes a role from the list of available self-assignable roles.

        **Usage:**
        `{prefix}selfrole remove <role>`

        **<role>:**
        - Mention the role, e.g., `@Blue Team`
        - Provide the role name, e.g., `Blue Team`
        - Provide the role ID.

        **Example:**
        `{prefix}selfrole remove Blue Team`
        """
        await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"selfroles": str(role.id)}})
        await ctx.send(f"Removed {role.mention} from selfroles.")

    @commands.check(selfrole_check)
    @selfrole.command(0, name="list")
    async def _list(self, ctx: commands.Context) -> None:
        """**Lists all self-assignable roles**

        This command displays a list of all roles that users can assign to themselves.

        **Usage:**
        `{prefix}selfrole list`
        """
        selfroles = (await self.bot.db.get_guild_config(ctx.guild.id)).selfroles
        roles = [ctx.guild.get_role(int(r)).name for r in selfroles]
        if roles:
            await ctx.send("Selfroles:\n" + "\n".join(roles))
        else:
            await ctx.send("No selfroles setup")

    @group(10, invoke_without_command=True)
    async def autorole(self, ctx: commands.Context) -> None:
        """**Manage roles automatically assigned to new members**

        This command group allows you to configure roles that are automatically given to users when they join the server.

        **Subcommands:**
        - `add` - Add a role to the list of autoroles.
        - `remove` - Remove a role from the list.
        - `list` - View all configured autoroles.
        """
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="autorole")

    @autorole.command(10, name="add")
    async def _add(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """**Add an autorole**

        This command adds a role to be automatically assigned to new members.

        **Usage:**
        `{prefix}autorole add <role>`

        **<role>:**
        - Mention the role, e.g., `@Member`
        - Provide the role name, e.g., `Member`
        - Provide the role ID.

        **Example:**
        `{prefix}autorole add Member`
        """
        if role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner.id:
            await ctx.send("User has insufficient permissions")
            return
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$addToSet": {"autoroles": str(role.id)}}
        )
        await ctx.send(f"Added {role.mention} as an autorole.")

    @autorole.command(10, name="remove", aliases=["del", "delete"])
    async def _remove(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """**Remove an autorole**

        This command removes a role from the list of autoroles.

        **Usage:**
        `{prefix}autorole remove <role>`

        **<role>:**
        - Mention the role, e.g., `@Member`
        - Provide the role name, e.g., `Member`
        - Provide the role ID.

        **Example:**
        `{prefix}autorole remove Member`
        """
        await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"autoroles": str(role.id)}})
        await ctx.send(f"Removed {role.mention} from autoroles.")

    @autorole.command(10, name="list")
    async def __list(self, ctx: commands.Context) -> None:
        """**Lists all autoroles**

        This command displays a list of all roles that are automatically assigned to new members.

        **Usage:**
        `{prefix}autorole list`
        """
        autoroles = (await self.bot.db.get_guild_config(ctx.guild.id)).autoroles
        roles = [ctx.guild.get_role(int(r)).name for r in autoroles]
        if roles:
            await ctx.send("Autoroles:\n" + "\n".join(roles))
        else:
            await ctx.send("No autoroles setup")

    @group(10, aliases=["reaction-role", "reaction_role"], invoke_without_command=True)
    async def reactionrole(self, ctx: commands.Context) -> None:
        """**Manage reaction roles**

        This command group allows you to set up roles that are assigned to users when they react to a message.

        **Subcommands:**
        - `add` - Add a reaction role to a message.
        - `remove` - Remove a reaction role from a message.
        """
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="reactionrole")

    @reactionrole.command(10, name="add")
    async def add_(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        message_id: int,
        emoji: EmojiOrUnicode,
        role: discord.Role,
    ) -> None:
        """**Add a reaction role to a message**

        This command links a role to an emoji on a specific message.
        When a user reacts with that emoji, they will be given the role.

        **Usage:**
        `{prefix}reactionrole add <#channel> <message_id> <emoji> <role>`

        **<#channel>:**
        The channel where the message is located.

        **<message_id>:**
        The ID of the message to add the reaction role to.

        **<emoji>:**
        The emoji that will trigger the role assignment.

        **<role>:**
        The role to be assigned.

        **Example:**
        `{prefix}reactionrole add #roles 123456789012345678 ✅ @Updates`
        """
        if role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner.id:
            await ctx.send("User has insufficient permissions")
            return

        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("Message not found.")
            return

        try:
            emoji_id = int(emoji.id)
        except ValueError:
            # Unicode emoji
            await msg.add_reaction(emoji.id)
        else:
            discord_emoji = self.bot.get_emoji(emoji_id)
            if discord_emoji is None:
                await ctx.send(
                    "The configured reaction role emoji is not available to the bot. "
                    "Please use an emoji the bot can access."
                )
                return
            await msg.add_reaction(discord_emoji)
        await self.bot.db.update_guild_config(
            ctx.guild.id,
            {
                "$addToSet": {
                    "reaction_roles": {
                        "message_id": str(message_id),
                        "emoji_id": str(emoji.id),
                        "role_id": str(role.id),
                    }
                }
            },
        )

        await ctx.send(
            f"Added reaction role: {role.mention} with emoji {emoji.id} to message {message_id}."
        )

    @reactionrole.command(10, name="remove", aliases=["del", "delete"])
    async def remove_(self, ctx: commands.Context, message_id: int, role: discord.Role) -> None:
        """**Remove a reaction role from a message**

        This command removes a reaction role configuration from a message.

        **Usage:**
        `{prefix}reactionrole remove <message_id> <role>`

        **<message_id>:**
        The ID of the message from which to remove the reaction role.

        **<role>:**
        The role associated with the reaction role to be removed.

        **Example:**
        `{prefix}reactionrole remove 123456789012345678 @Updates`
        """
        try:
            role_info = (await self.bot.db.get_guild_config(ctx.guild.id)).reaction_roles.get_kv(
                "message_id", str(message_id)
            )
        except IndexError:
            await ctx.send("No role/emoji pair found for that message.")
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$pull": {"reaction_roles": role_info}}
        )
        await ctx.send(f"Removed reaction role {role.mention} from message {message_id}.")

    @Cog.listener()
    async def on_member_join(self, m: discord.Member) -> None:
        """Assign autoroles"""
        autoroles = (await self.bot.db.get_guild_config(m.guild.id)).autoroles
        roles = [m.guild.get_role(int(r)) for r in autoroles]
        if roles:
            await m.add_roles(*roles, reason="Autoroles")

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Add reaction roles"""
        reaction_roles = (await self.bot.db.get_guild_config(payload.guild_id)).reaction_roles
        emoji_id = payload.emoji.id or str(payload.emoji)
        msg_roles = list(
            filter(
                lambda r: int(r.message_id) == payload.message_id
                and tryint(r.emoji_id) == emoji_id,
                reaction_roles,
            )
        )

        if msg_roles:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(int(msg_roles[0].role_id))
            await member.add_roles(role, reason="Reaction Role")

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Remove reaction roles"""
        reaction_roles = (await self.bot.db.get_guild_config(payload.guild_id)).reaction_roles
        emoji_id = payload.emoji.id or str(payload.emoji)
        msg_roles = list(
            filter(
                lambda r: int(r.message_id) == payload.message_id
                and tryint(r.emoji_id) == emoji_id,
                reaction_roles,
            )
        )

        if len(msg_roles) == 1:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(int(msg_roles[0].role_id))
            await member.remove_roles(role, reason="Reaction Role")

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Removes any autoroles, selfroles, or reaction roles that are deleted"""
        guild_config = await self.bot.db.get_guild_config(role.guild.id)
        db_keys = ["selfroles", "autoroles", "reaction_roles"]
        for k in db_keys:
            if str(role.id) in getattr(guild_config, k):
                await self.bot.db.update_guild_config(role.guild.id, {"$pull": {k: str(role.id)}})


async def setup(bot: rainbot) -> None:
    await bot.add_cog(Roles(bot))

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
        """Give yourself a role!"""
        selfroles = (await self.bot.db.get_guild_config(ctx.guild.id)).selfroles
        if str(role.id) not in selfroles:
            await ctx.send(f'{role.name} is not an available selfrole.')
            return
        if role in ctx.author.roles:
            await ctx.author.remove_roles(role, reason='Selfrole')
            await ctx.send(f'Removed role {self.bot.accept}')
        else:
            await ctx.author.add_roles(role, reason='Selfrole')
            await ctx.send(f'Added role {self.bot.accept}')

    @selfrole.command(10)
    async def add(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add a selfrole for users to give themselves"""
        if role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner.id:
            await ctx.send('User has insufficient permissions')
            return
        await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {'selfroles': str(role.id)}})
        await ctx.send(self.bot.accept)

    @selfrole.command(10, aliases=['del', 'delete'])
    async def remove(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Remove a selfrole"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'selfroles': str(role.id)}})
        await ctx.send(self.bot.accept)

    @commands.check(selfrole_check)
    @selfrole.command(0, name='list')
    async def _list(self, ctx: commands.Context) -> None:
        """Lists all possible selfroles"""
        selfroles = (await self.bot.db.get_guild_config(ctx.guild.id)).selfroles
        roles = [ctx.guild.get_role(int(r)).name for r in selfroles]
        if roles:
            await ctx.send('Selfroles:\n' + '\n'.join(roles))
        else:
            await ctx.send('No selfroles setup')

    @group(10, invoke_without_command=True)
    async def autorole(self, ctx: commands.Context) -> None:
        """Manage autoroles"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='autorole')

    @autorole.command(10, name='add')
    async def _add(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add a role to the list of autoroles"""
        if role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner.id:
            await ctx.send('User has insufficient permissions')
            return
        await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {'autoroles': str(role.id)}})
        await ctx.send(self.bot.accept)

    @autorole.command(10, name='remove', aliases=['del', 'delete'])
    async def _remove(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Remove a selfrole"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'autoroles': str(role.id)}})
        await ctx.send(self.bot.accept)

    @autorole.command(10, name='list')
    async def __list(self, ctx: commands.Context) -> None:
        """Lists all possible autoroles"""
        autoroles = (await self.bot.db.get_guild_config(ctx.guild.id)).autoroles
        roles = [ctx.guild.get_role(int(r)).name for r in autoroles]
        if roles:
            await ctx.send('Autoroles:\n' + '\n'.join(roles))
        else:
            await ctx.send('No autoroles setup')

    @group(10, aliases=['reaction-role', 'reaction_role'], invoke_without_command=True)
    async def reactionrole(self, ctx: commands.Context) -> None:
        """Manage reaction roles."""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='reactionrole')

    @reactionrole.command(10, name='add')
    async def add_(self, ctx: commands.Context, channel: discord.TextChannel, message_id: int, emoji: EmojiOrUnicode, role: discord.Role) -> None:
        """Add 1 role/emoji pair to a message"""
        if role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner.id:
            await ctx.send('User has insufficient permissions')
            return

        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send('Message not found.')
            return

        try:
            reaction = f'reaction_role:{int(emoji.id)}'
        except ValueError:
            reaction = emoji.id
        await msg.add_reaction(reaction)
        await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {'reaction_roles': {
            'message_id': str(message_id),
            'emoji_id': str(emoji.id),
            'role_id': str(role.id)
        }}})

        await ctx.send(self.bot.accept)

    @reactionrole.command(10, name='remove', aliases=['del', 'delete'])
    async def remove_(self, ctx: commands.Context, message_id: int, role: discord.Role) -> None:
        """Remove a role/emoji pair from a message"""
        try:
            role_info = (await self.bot.db.get_guild_config(ctx.guild.id)).reaction_roles.get_kv('message_id', str(message_id))
        except IndexError:
            await ctx.send('No role/emoji pair found for that message.')
            return

        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'reaction_roles': role_info}})
        await ctx.send(self.bot.accept)

    @Cog.listener()
    async def on_member_join(self, m: discord.Member) -> None:
        """Assign autoroles"""
        autoroles = (await self.bot.db.get_guild_config(m.guild.id)).autoroles
        roles = [m.guild.get_role(int(r)) for r in autoroles]
        if roles:
            await m.add_roles(*roles, reason='Autoroles')

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Add reaction roles"""
        reaction_roles = (await self.bot.db.get_guild_config(payload.guild_id)).reaction_roles
        emoji_id = payload.emoji.id or str(payload.emoji)
        msg_roles = list(filter(lambda r: int(r.message_id) == payload.message_id and tryint(r.emoji_id) == emoji_id, reaction_roles))

        if msg_roles:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(int(msg_roles[0].role_id))
            await member.add_roles(role, reason='Reaction Role')

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Remove reaction roles"""
        reaction_roles = (await self.bot.db.get_guild_config(payload.guild_id)).reaction_roles
        emoji_id = payload.emoji.id or str(payload.emoji)
        msg_roles = list(filter(lambda r: int(r.message_id) == payload.message_id and tryint(r.emoji_id) == emoji_id, reaction_roles))

        if len(msg_roles) == 1:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(int(msg_roles[0].role_id))
            await member.remove_roles(role, reason='Reaction Role')

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Removes any autoroles, selfroles, or reaction roles that are deleted"""
        guild_config = await self.bot.db.get_guild_config(role.guild.id)
        db_keys = ['selfroles', 'autoroles', 'reaction_roles']
        for k in db_keys:
            if str(role.id) in getattr(guild_config, k):
                await self.bot.db.update_guild_config(role.guild.id, {'$pull': {k: str(role.id)}})


def setup(bot: rainbot) -> None:
    bot.add_cog(Roles(bot))

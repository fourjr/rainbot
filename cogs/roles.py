import discord
from discord.ext import commands
from discord.ext.commands import Cog

from ext.command import group


class Roles(commands.Cog):
    """Set up roles that users can get"""

    def __init__(self, bot):
        self.bot = bot

    @group(0, invoke_without_command=True)
    async def selfrole(self, ctx, *, role: discord.Role):
        """Give yourself a role!"""
        selfroles = (await self.bot.db.get_guild_config(ctx.guild.id)).selfroles
        if len(selfroles) == 0:
            return
        if role.id not in selfroles:
            return await ctx.send(f'{role.name} is not an available selfrole.')
        if role in ctx.author.roles:
            await ctx.author.remove_roles(role, reason='Selfrole')
            await ctx.send(f'Removed role {self.bot.accept}')
        else:
            await ctx.author.add_roles(role, reason='Selfrole')
            await ctx.send(f'Added role {self.bot.accept}')

    @selfrole.command(8)
    async def add(self, ctx, *, role: discord.Role):
        """Add a selfrole for users to give themselves"""
        if role.position >= ctx.author.top_role.position:
            return await ctx.send('User has insufficient permissions')
        await self.bot.db.update_guild_config(ctx.guild.id, {'$push': {'selfroles': role.id}})
        await ctx.send(self.bot.accept)

    @selfrole.command(8, aliases=['del', 'delete'])
    async def remove(self, ctx, *, role: discord.Role):
        """Remove a selfrole"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'selfroles': role.id}})
        await ctx.send(self.bot.accept)

    @group(8)
    async def autorole(self, ctx):
        """Manage autoroles"""

    @autorole.command(8, name='add')
    async def _add(self, ctx, *, role: discord.Role):
        """Add a role to the list of autoroles"""
        if role.position >= ctx.author.top_role.position:
            return await ctx.send('User has insufficient permissions')
        await self.bot.db.update_guild_config(ctx.guild.id, {'$push': {'autoroles': role.id}})
        await ctx.send(self.bot.accept)

    @autorole.command(8, name='remove', aliases=['del', 'delete'])
    async def _remove(self, ctx, *, role: discord.Role):
        """Remove a selfrole"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'autoroles': role.id}})
        await ctx.send(self.bot.accept)

    @Cog.listener()
    async def on_member_join(self, m):
        """Assign autoroles"""
        autoroles = (await self.bot.db.get_guild_config(m.guild.id)).autoroles
        roles = [m.guild.get_role(r) for r in autoroles]
        if roles:
            await m.add_roles(*roles, reason='Autoroles')

    @Cog.listener()
    async def on_guild_role_delete(self, role):
        """Removes any autoroles, selfroles, or reaction roles that are deleted"""
        guild_config = await self.bot.db.get_guild_config(role.guild.id)
        db_keys = ['selfroles', 'autoroles', 'reaction_roles']
        for k in db_keys:
            if role.id in getattr(guild_config, k):
                await self.bot.db.update_guild_config(role.guild.id, {'$pull': {k: role.id}})


def setup(bot):
    bot.add_cog(Roles(bot))

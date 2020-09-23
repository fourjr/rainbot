import discord
from discord.ext import commands

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


def setup(bot):
    bot.add_cog(Roles(bot))

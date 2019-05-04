import discord
from ext.command import group
from ext.utils import random_color
from ext.time import UserFriendlyTime


class Giveaways:
    # TODO: HAVE A TIMER AND ROLL ONCE TIME IS UP
    # TODO: EDIT THE DESCRIPTION
    # TODO: DETECT IF THE MSG
    # TODO: REROLL CMD
    # TODO: STATS (NEW MEMBERS ATTRACTED, NEW ACCS CREATED)
    def __init__(self, bot):
        self.bot = bot

    @group(8, invoke_without_command=True)
    async def giveaway(self, ctx):
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='giveaway')

    @giveaway.command(8)
    async def create(self, ctx, *, time: UserFriendlyTime):
        em = discord.Embed(title='New Giveaway!', description=time.arg, color=random_color(), timestamp=time.dt)
        em.set_footer(text='Ends at')
        await ctx.send(discord.utils.get(ctx.guild.roles, id=574117534794514432).mention, embed=em)
        # TODO: SEND IN CHANNEL
        # TODO: ADD REACTION
        # TODO: REACTION IS A GIF


def setup(bot):
    bot.add_cog(Giveaways(bot))

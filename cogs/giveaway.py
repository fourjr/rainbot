import asyncio
import discord
import random

from discord.ext import commands
from datetime import datetime
from ext.command import group
from ext.utils import random_color
from ext.time import UserFriendlyTime


ACTIVE_COLOR = 0x01dc5a
INACTIVE_COLOR = 0xe8330f


class Giveaways:

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.channel: discord.TextChannel = None
        bot.loop.create_task(self.__ainit__())

    async def __ainit__(self):
        """Setup constants"""
        await self.bot.wait_until_ready()
        self.channel = self.bot.get_channel(574113478588235796)
        self.role = discord.utils.get(self.channel.guild.roles, id=574117534794514432)

        latest_giveaway = await self.get_latest_giveaway()
        if latest_giveaway:
            self.bot.loop.create_task(self.queue_roll(latest_giveaway))

    async def get_latest_giveaway(self, *, force=False) -> discord.Message:
        """Gets the latest giveaway message.

        If force is False, it returns None if there is no current active giveaway
        """
        message = await self.channel.history(limit=20).find(lambda m: m.embeds and m.embeds[0].title == 'New Giveaway!')
        if force or (message and message.embeds[0].color.value == ACTIVE_COLOR):
            return message

    async def roll_winner(self, nwinners=None) -> str:
        """Rolls winner(s) and returns a list of discord.Member
        
        Supports nwinners as an arg. Defaults to check giveaway message
        """
        latest_giveaway = await self.get_latest_giveaway(force=True)

        nwinners = nwinners or int(latest_giveaway.embeds[0].description.split(' ')[0][2:])
        participants = await next(r for r in latest_giveaway.reactions if getattr(r.emoji, 'id', None) == 576063377097359381).users().filter(
            lambda m: not m.bot and isinstance(m, discord.Member)
        ).flatten()

        winners = random.sample(participants, nwinners)
        return winners

    async def queue_roll(self, giveaway: discord.Message):
        """Queues up the autoroll."""
        time = (giveaway.embeds[0].timestamp - datetime.utcnow()).total_seconds()
        await asyncio.sleep(time)

        try:
            winners = await self.roll_winner()
        except ValueError:
            winners = None
            await giveaway.channel.send('Not enough participants :(')
        else:
            fmt_winners = '\n'.join({i.mention for i in winners})
            description = '\n'.join(giveaway.embeds[0].description.split('\n')[1:])
            await giveaway.channel.send(f"Congratulations! Here are the winners for `{description}` <a:bahrooHi:402250652996337674>\n{fmt_winners}")

        new_embed = giveaway.embeds[0]
        new_embed.title = 'Ended Giveaway'
        if winners:
            new_embed.description += f'\n\n**__Winners:__**\n{fmt_winners}'

        new_embed.color = INACTIVE_COLOR
        await giveaway.edit(embed=new_embed)

    @group(8, invoke_without_command=True, aliases=['give'])
    async def giveaway(self, ctx):
        """Setup giveaways!"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='giveaway')

    @giveaway.command(8, usage='<endtime> <winners> <description>')
    async def create(self, ctx, *, time: UserFriendlyTime):
        """Create a giveaway

        Example: `!giveaway create 3 days 5 $10USD`
        """
        async with ctx.typing():
            latest_giveaway = await self.get_latest_giveaway()
            if not latest_giveaway:
                try:
                    winners = max(int(time.arg.split(' ')[0]), 1)
                except ValueError as e:
                    raise commands.BadArgument('Converting to "int" failed for parameter "winnners".') from e

                description = ' '.join(time.arg.split(' ')[1:])
                em = discord.Embed(
                    title='New Giveaway!',
                    description=f"__{winners} winner{'s' if winners > 1 else ''}__\n{description}",
                    color=ACTIVE_COLOR,
                    timestamp=time.dt
                )
                em.set_footer(text='End Time')
                await self.role.edit(mentionable=True)
                message = await self.channel.send(self.role.mention, embed=em)
                await self.role.edit(mentionable=False)
                await message.add_reaction('giveaway:576063377097359381')
                await ctx.send(f'Created: {message.jump_url}')
                self.bot.loop.create_task(self.queue_roll(message))
            else:
                await ctx.send('A giveaway already exists. Please wait until the current one expires.')

    @giveaway.command(6, aliases=['stat', 'statistics'])
    async def stats(self, ctx):
        """View statistics of the latest giveaway"""
        async with ctx.typing():
            latest_giveaway = await self.get_latest_giveaway(force=True)
            ended_at = latest_giveaway.embeds[0].timestamp

            now = datetime.utcnow()
            em = discord.Embed(
                title='Giveaway Stats',
                description=f'[Jump to Giveaway]({latest_giveaway.jump_url})\n{latest_giveaway.embeds[0].description}',
                color=random_color(),
                timestamp=now
            )

            participants = await next(r for r in latest_giveaway.reactions if getattr(r.emoji, 'id', None) == 576063377097359381).users().filter(lambda m: not m.bot).flatten()
            new_members = {i for i in ctx.guild.members if i.joined_at > latest_giveaway.created_at and i.joined_at < ended_at and i in participants}
            new_accounts = {i for i in new_members if i.created_at > latest_giveaway.created_at}

            em.add_field(name='Member Stats', value='\n'.join((
                f'Giveaway created `{now - latest_giveaway.created_at}` ago',
                f'Total Participants: {len(participants)}',  # minus rain
                f'New Members Joined: {len(new_members)} ({len(new_accounts)} are just created!)'
            )))

            await ctx.send(embed=em)

    @giveaway.command(8)
    async def edit(self, ctx, *, description):
        """Edit the description of the latest giveaway"""
        latest_giveaway = await self.get_latest_giveaway()
        if latest_giveaway:
            new_embed = latest_giveaway.embeds[0]
            new_embed.description = description
            latest_giveaway.edit(embed=new_embed)
            await ctx.send(f'Edited: {latest_giveaway.jump_url}')
        else:
            await ctx.send('No active giveaway')

    @giveaway.command(8)
    async def reroll(self, ctx, nwinners=None):
        async with ctx.typing():
            latest_giveaway = await self.get_latest_giveaway(force=True)
            if latest_giveaway:
                try:
                    winners = await self.roll_winner()
                except ValueError:
                    await ctx.send('Not enough participants :(')
                else:
                    fmt_winners = '\n'.join({i.mention for i in winners})
                    description = '\n'.join(latest_giveaway.embeds[0].description.split('\n')[1:])
                    await ctx.send(f"Congratulations! Here are the **rerolled** winners for `{description}` <a:bahrooHi:402250652996337674>\n{fmt_winners}")
            else:
                await ctx.send('No active giveaway')


def setup(bot):
    bot.add_cog(Giveaways(bot))

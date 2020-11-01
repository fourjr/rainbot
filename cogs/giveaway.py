import asyncio
import random
from typing import Dict, List, Union, Optional

import discord
from discord.ext import commands

from bot import rainbot
from ext.command import command, group
from ext.time import UserFriendlyTime
from ext.utils import EmojiOrUnicode


ACTIVE_COLOR = 0x01dc5a
INACTIVE_COLOR = 0xe8330f


class Giveaways(commands.Cog):
    """Sets up giveaways!"""

    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        bot.loop.create_task(self.__ainit__())
        self.order = 3
        self.queue: Dict[int, asyncio.Task] = {}

    async def __ainit__(self) -> None:
        """Setup constants"""
        await self.bot.wait_until_ready()
        for i in self.bot.guilds:
            latest_giveaway = await self.get_latest_giveaway(guild_id=i.id)

            if latest_giveaway:
                self.queue[latest_giveaway.id] = self.bot.loop.create_task(self.queue_roll(latest_giveaway))

    async def channel(self, ctx: commands.Context=None, *, guild_id: int=None) -> Optional[discord.TextChannel]:
        guild_id = guild_id or ctx.guild.id
        guild_config = await self.bot.db.get_guild_config(guild_id)
        if guild_config['giveaway']['channel_id']:
            return self.bot.get_channel(int(guild_config['giveaway']['channel_id']))
        return None

    async def role(self, ctx: commands.Context) -> Optional[discord.Role]:
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if guild_config.giveaway.role_id:
            role_id = guild_config.giveaway.role_id
            if role_id is None:
                return None
            elif role_id in ('@everyone', '@here'):
                return role_id
            return discord.utils.get(ctx.guild.roles, id=int(role_id))
        return None

    async def emoji(self, ctx: commands.Context) -> Union[int, str, None]:
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if guild_config.giveaway.emoji_id:
            emoji_id = guild_config.giveaway.emoji_id
            try:
                return f'giveaway:{int(emoji_id)}'
            except ValueError:
                return emoji_id
        return None

    async def get_latest_giveaway(self, ctx: commands.Context=None, *, force: bool=False, guild_id: int=None) -> Optional[discord.Message]:
        """Gets the latest giveaway message.

        If force is False, it returns None if there is no current active giveaway
        """
        try:
            guild_config = await self.bot.db.get_guild_config(guild_id or ctx.guild.id)
            if guild_config.giveaway.message_id:
                channel = await self.channel(ctx, guild_id=guild_id)
                try:
                    return await channel.fetch_message(guild_config.giveaway.message_id)
                except (discord.NotFound, AttributeError):
                    await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'giveaway.message_id': None}})
                    return None
        except discord.Forbidden:
            return None
        return None

    async def roll_winner(self, ctx: commands.Context, nwinners: int=None) -> List[str]:
        """Rolls winner(s) and returns a list of discord.Member

        Supports nwinners as an arg. Defaults to check giveaway message
        """
        latest_giveaway = await self.get_latest_giveaway(ctx, force=True)

        nwinners = nwinners or int(latest_giveaway.embeds[0].description.split(' ')[0][2:])
        emoji_id = await self.emoji(ctx)
        participants = await next(r for r in latest_giveaway.reactions if getattr(r.emoji, 'id', r.emoji) == emoji_id).users().filter(
            lambda m: not m.bot and isinstance(m, discord.Member)
        ).flatten()

        winners = random.sample(participants, nwinners)
        return winners

    async def queue_roll(self, giveaway: discord.Message) -> None:
        """Queues up the autoroll."""
        time = (giveaway.embeds[0].timestamp - giveaway.created_at).total_seconds()
        await asyncio.sleep(time)

        await self.end_giveaway(giveaway)

    async def end_giveaway(self, giveaway) -> None:
        try:
            winners = await self.roll_winner(giveaway)
        except (RuntimeError, ValueError):
            winners = None
            await giveaway.channel.send('Not enough participants :(')
        else:
            fmt_winners = '\n'.join({i.mention for i in winners})
            description = '\n'.join(giveaway.embeds[0].description.split('\n')[1:])
            await giveaway.channel.send(f"Congratulations! Here are the winners for `{description}` <a:bahrooHi:402250652996337674>\n{fmt_winners}")

        new_embed = giveaway.embeds[0]
        new_embed.title = 'Giveaway Ended'
        if winners:
            new_embed.description += f'\n\n**__Winners:__**\n{fmt_winners}'

        new_embed.color = INACTIVE_COLOR
        await giveaway.edit(embed=new_embed)
        await self.bot.db.update_guild_config(giveaway.guild.id, {'$set': {'giveaway.message_id': None}})

    @command(10, aliases=['set-giveaway' 'set_giveaway'])
    async def setgiveaway(self, ctx: commands.Context, emoji: EmojiOrUnicode, channel: discord.TextChannel, role: str=None):
        """Sets up giveaways.

        Role can be @everyone, @here or none"""
        if role == 'none' or role is None:
            role_id = None
        elif role in ('@everyone', '@here'):
            role_id = role
        else:
            role_id = (await commands.RoleConverter().convert(ctx, role)).id

        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {
            'giveaway.emoji_id': str(emoji.id),
            'giveaway.channel_id': str(channel.id),
            'giveaway.role_id': role_id
        }})

        await ctx.send(self.bot.accept)

    @group(6, invoke_without_command=True, aliases=['give'])
    async def giveaway(self, ctx: commands.Context) -> None:
        """Setup giveaways!"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='giveaway')

    @giveaway.command(8, usage='<endtime> <winners> <description>')
    async def create(self, ctx: commands.Context, *, time: UserFriendlyTime) -> None:
        """Create a giveaway

        Example: `!giveaway create 3 days 5 $10USD`
        """
        async with ctx.typing():
            latest_giveaway = await self.get_latest_giveaway(ctx)
            if not latest_giveaway:
                try:
                    winners = max(int(time.arg.split(' ')[0]), 1)
                except ValueError as e:
                    raise commands.BadArgument('Converting to "int" failed for parameter "winners".') from e

                # Check if the giveaway exusts
                guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                if not guild_config.giveaway.channel_id:
                    await ctx.invoke(self.bot.get_command('help'), command_or_cog='setgiveaway', error=Exception('Setup giveaways with setgiveaway first.'))
                    return

                if not time.arg:
                    raise commands.BadArgument('Converting to "str" failed for parameter "description".')
                description = ' '.join(time.arg.split(' ')[1:])
                em = discord.Embed(
                    title='New Giveaway!',
                    description=f"__{winners} winner{'s' if winners > 1 else ''}__\n{description}",
                    color=ACTIVE_COLOR,
                    timestamp=time.dt
                )
                em.set_footer(text='End Time')
                role = await self.role(ctx)
                channel = await self.channel(ctx)
                emoji = await self.emoji(ctx)

                if isinstance(role, discord.Role):
                    message = await channel.send(role.mention, embed=em)
                elif isinstance(role, str):
                    message = await channel.send(role, embed=em)
                else:
                    message = await channel.send(embed=em)

                await message.add_reaction(emoji)

                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'giveaway.message_id': str(message.id)}})

                await ctx.send(f'Created: {message.jump_url}')
                self.bot.loop.create_task(self.queue_roll(message))
            else:
                await ctx.send('A giveaway already exists. Please wait until the current one expires.')

    @giveaway.command(6, aliases=['stat', 'statistics'])
    async def stats(self, ctx: commands.Context) -> None:
        """View statistics of the latest giveaway"""
        async with ctx.typing():
            latest_giveaway = await self.get_latest_giveaway(ctx, force=True)
            if latest_giveaway:
                now = ctx.message.created_at
                ended_at = latest_giveaway.embeds[0].timestamp
                ended = latest_giveaway.embeds[0].color.value == INACTIVE_COLOR
                if ended:
                    ended = f'Giveaway ended `{now - ended_at}` ago\n'
                else:
                    ended = ''

                em = discord.Embed(
                    title='Giveaway Stats ' + ('(Ended)' if ended else ''),
                    description=f'[Jump to Giveaway]({latest_giveaway.jump_url})\n{latest_giveaway.embeds[0].description}',
                    color=latest_giveaway.embeds[0].color,
                    timestamp=now
                )

                emoji_id = await self.emoji(ctx)
                participants = await next(r for r in latest_giveaway.reactions if getattr(r.emoji, 'id', r.emoji) == emoji_id).users().filter(lambda m: not m.bot).flatten()
                new_members = {i for i in ctx.guild.members if i.joined_at > latest_giveaway.created_at and i.joined_at < ended_at and i in participants}
                new_accounts = {i for i in new_members if i.created_at > latest_giveaway.created_at}

                em.add_field(name='Member Stats', value='\n'.join((
                    f'Giveaway created `{now - latest_giveaway.created_at}` ago',
                    ended,
                    f'Total Participants: {len(participants)}',  # minus rain
                    f'New Members Joined: {len(new_members)} ({len(new_accounts)} are just created!)'
                )))

                await ctx.send(embed=em)
            else:
                await ctx.send('No giveaway found')

    @giveaway.command(8, aliases=['edit-description'])
    async def edit_description(self, ctx: commands.Context, *, description: str) -> None:
        """Edit the description of the latest giveaway"""
        latest_giveaway = await self.get_latest_giveaway(ctx)
        if latest_giveaway:
            new_embed = latest_giveaway.embeds[0]
            new_embed.description = new_embed.description.split('\n')[0] + '\n' + description
            await latest_giveaway.edit(embed=new_embed)
            await ctx.send(f'Edited: {latest_giveaway.jump_url}')
        else:
            await ctx.send('No active giveaway')

    @giveaway.command(8, aliases=['edit-winners'])
    async def edit_winners(self, ctx: commands.Context, *, winners: int) -> None:
        """Edit the number of winners of the latest giveaway"""
        latest_giveaway = await self.get_latest_giveaway(ctx)
        if latest_giveaway:
            new_embed = latest_giveaway.embeds[0]
            new_embed.description = f"__{winners} winner{'s' if winners > 1 else ''}__" + '\n' + '\n'.join(new_embed.description.split('\n')[1:])
            await latest_giveaway.edit(embed=new_embed)
            await ctx.send(f'Edited: {latest_giveaway.jump_url}')
        else:
            await ctx.send('No active giveaway')

    @giveaway.command(8, aliases=['roll'])
    async def reroll(self, ctx: commands.Context, nwinners: int=None) -> None:
        """Rerolls the winners"""
        async with ctx.typing():
            latest_giveaway = await self.get_latest_giveaway(ctx, force=True)
            if latest_giveaway:
                try:
                    winners = await self.roll_winner(ctx)
                except ValueError:
                    await ctx.send('Not enough participants :(')
                else:
                    fmt_winners = '\n'.join({i.mention for i in winners})
                    description = '\n'.join(latest_giveaway.embeds[0].description.split('\n')[1:])
                    await ctx.send(f"Congratulations! Here are the **rerolled** winners for `{description}` <a:bahrooHi:402250652996337674>\n{fmt_winners}")
            else:
                await ctx.send('No active giveaway')

    @giveaway.command(6)
    async def stop(self, ctx: commands.Context) -> None:
        """Stops the giveaway"""
        latest_giveaway = await self.get_latest_giveaway(ctx, force=True)
        try:
            self.queue[latest_giveaway.id].cancel()
            del self.queue[latest_giveaway.id]
        except KeyError:
            pass
        await self.end_giveaway(latest_giveaway)
        await ctx.send(self.bot.accept)


def setup(bot: rainbot) -> None:
    bot.add_cog(Giveaways(bot))

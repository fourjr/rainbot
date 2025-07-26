import json
import string
from collections import defaultdict
from typing import Union

import discord
from box import Box
from discord.ext import commands

from ext.command import command
from ext.database import DEFAULT
from ext.utility import SafeFormat, SafeString


class EventsAnnouncer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_cache = defaultdict(set)
        bot.loop.create_task(self.populate_invite_cache())

    async def populate_invite_cache(self):
        await self.bot.wait_until_ready()
        for g in self.bot.guilds:
            try:
                self.invite_cache[g.id] = {i for i in await g.invites()}
            except discord.Forbidden:
                pass

    async def get_used_invite(self, guild):
        """Checks which invite is used in join via the following strategies:
        1. Check if invite doesn't exist anymore
        2. Check invite uses
        """
        try:
            update_invite_cache = {i for i in await guild.invites()}
        except discord.Forbidden:
            return Box(default_box=True, default_box_attr='{unable to get invite}')

        for i in self.invite_cache[guild.id]:
            if i in update_invite_cache:
                # pass check 1
                try:
                    new_invite = next(inv for inv in update_invite_cache if inv.id == inv.id)
                except StopIteration:
                    continue
                else:
                    if new_invite.uses > i.uses:
                        return new_invite
        return Box(default_box=True, default_box_attr='{unable to get invite}')

    def apply_vars(self, member, message, invite):
        return string.Formatter().vformat(message, [], SafeFormat(
            member=member,
            guild=member.guild,
            bot=self.bot.user,
            invite=invite
        ))

    def apply_vars_dict(self, member, message, invite):
        for k, v in message.items():
            if isinstance(v, dict):
                message[k] = self.apply_vars_dict(member, v, invite)
            elif isinstance(v, str):
                message[k] = self.apply_vars(member, v, invite)
            elif isinstance(v, list):
                message[k] = [self.apply_vars_dict(member, _v, invite) for _v in v]
            if k == 'timestamp':
                message[k] = v[:-1]
        return message

    def format_message(self, member, message, invite=None):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            # message is not embed
            message = self.apply_vars(member, message, invite)
            message = {'content': message}
        else:
            # message is embed
            message = self.apply_vars_dict(member, message, invite)

            if any(i in message for i in ('embed', 'content')):
                message['embed'] = discord.Embed.from_dict(message['embed'])
            else:
                message = None
        return message

    @command(10, aliases=['set-announcement', 'set_announcement'])
    async def setannouncement(self, ctx, event_type: str, channel: Union[discord.TextChannel, str.lower]=None, *, message=None):
        """Sets up events announcer. Check [here](https://github.com/fourjr/rainbot/wiki/Events-Announcer)
        for complex usage.

        Valid event types: member_join, member_remove

        Set channel to "dm" to dm user

        Example usage: `eventsannounce #general Hello {member.name}`
        """

        if event_type not in DEFAULT['events_announce'].keys():
            raise commands.BadArgument(f'Invalid event, pick from {", ".join(DEFAULT["events_announce"].keys())}')

        if not isinstance(channel, discord.TextChannel) and channel != 'dm':
            raise commands.BadArgument('Invalid channel, #mention a channel or "dm".')

        if message is None:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'events_announce': {event_type: {}}}})
            await ctx.send(self.bot.accept)
        else:
            if message.startswith('https://') or message.startswith('http://'):
                # message is a URL
                if message.startswith('https://hastebin.cc/'):
                    message = 'https://hastebin.cc/raw/' + message.split('/')[-1]

                async with self.bot.session.get(message) as resp:
                    message = await resp.text(encoding='utf8')

            formatted_message = self.format_message(ctx.author, message, SafeString('{invite}'))
            if formatted_message:
                if channel == 'dm':
                    await ctx.author.send(**formatted_message)
                else:
                    await channel.send(**formatted_message)
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'events_announce': {event_type: {'channel_id': str(getattr(channel, 'id', None)), 'message': message}}}})
                await ctx.send(f'Message sent to {getattr(channel, "mention", "DM")} for testing.\nNote: invites cannot be rendered in test message')
            else:
                await ctx.send('Invalid welcome message syntax.')

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.bot.dev_mode:
            guild_config = await self.bot.db.get_guild_config(member.guild.id)
            config = guild_config.events_announce.member_join
            invite = await self.get_used_invite(member.guild)
            if config:
                if config['channel_id'] == 'dm':
                    channel = member
                else:
                    channel = member.guild.get_channel(int(config['channel_id']))
                if channel:
                    message = self.format_message(member, config['message'], invite)
                    if message:
                        await channel.send(**message)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not self.bot.dev_mode:
            guild_config = await self.bot.db.get_guild_config(member.guild.id)
            config = guild_config.events_announce.member_remove
            if config:
                if config['channel_id'] == 'dm':
                    channel = member
                else:
                    channel = member.guild.get_channel(int(config['channel_id']))
                if channel:
                    message = self.format_message(member, config['message'])
                    if message:
                        await channel.send(**message)


async def setup(bot):
    await bot.add_cog(EventsAnnouncer(bot))

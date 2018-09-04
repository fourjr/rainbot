import copy
import json

import discord
from discord.ext import commands

from ext.errors import BotMissingPermissionsInChannel
from ext.utils import lower
from ext.command import command, group


class Setup:
    """Setting up rainbot: https://github.com/fourjr/rainbot/wiki/Setting-up-rainbot"""

    def __init__(self, bot):
        self.bot = bot
        self.default = {
            'guild_id': None,
            'logs': {
                'message_delete': None,
                'message_edit': None,
                'member_join': None,
                'member_remove': None,
                'member_ban': None,
                'member_unban': None,
                'vc_state_change': None,
                'channel_create': None,
                'channel_delete': None,
                'role_create': None,
                'role_delete': None
            },
            'modlog': {
                'member_mute': None,
                'member_unmute': None,
                'member_kick': None,
                'member_ban': None,
                'member_unban': None,
                'member_softban': None,
                'message_purge': None
            },
            'time_offset': 0,
            'detections': {
                'filters': [],
                'block_invite': False,
                'mention_limit': None,
                'spam_detection': None,
            },
            'perm_levels': {},
            'mute_role': None,
            'mutes': [],
            'prefix': '!!'
        }

    async def on_guild_join(self, guild):
        default = copy.copy(self.default)
        default['guild_id'] = str(guild.id)
        await self.bot.mongo.config.guilds.insert_one(default)

    @command(6, aliases=['view_config', 'view-config'])
    async def viewconfig(self, ctx):
        """View the current guild configuration"""
        guild_info = await self.bot.mongo.config.guilds.find_one({'guild_id': str(ctx.guild.id)}) or {'_id': None}
        del guild_info['_id']
        try:
            await ctx.send(f'```json\n{json.dumps(guild_info, indent=2)}\n```')
        except discord.HTTPException:
            async with self.bot.session.post('https://hastebin.com/documents', data=json.dumps(guild_info, indent=4)) as resp:
                await ctx.send(f"Your server's configuration: https://hastebin.com/{(await resp.json())['key']}")

    @command(10, alises=['set_log', 'set-log'])
    async def setlog(self, ctx, log_name: lower, channel: discord.TextChannel=None):
        """Sets the log channel for various types of logging

        Valid types: all, message_delete, message_edit, member_join, member_remove, member_ban, member_unban, vc_state_change, channel_create, channel_delete, role_create, role_delete
        """
        valid_logs = self.default['logs'].keys()
        channel_id = None
        if channel:
            try:
                await channel.send('Testing the logs')
            except discord.Forbidden:
                raise BotMissingPermissionsInChannel(['send_messages'], channel)
            channel_id = str(channel.id)

        if log_name == 'all':
            for i in valid_logs:
                await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'logs.{i}': channel_id}}, upsert=True)
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument('Invalid log name, pick one from below:\n' + ', '.join(valid_logs))

            await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'logs.{log_name}': channel_id}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, alises=['set_modlog', 'set-modlog'])
    async def setmodlog(self, ctx, log_name: lower, channel: discord.TextChannel=None):
        """Sets the log channel for various types of logging

        Valid types: all, member_mute, member_unmute, member_kick, member_ban, member_unban, member_softban, message_purge
        """
        channel_id = None
        if channel:
            try:
                await channel.send('Testing the logs')
            except discord.Forbidden:
                raise BotMissingPermissionsInChannel(['send_messages'], channel)
            channel_id = str(channel.id)

        valid_logs = self.default['modlog'].keys()
        if log_name == 'all':
            for i in valid_logs:
                await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'modlog.{i}': channel_id}}, upsert=True)
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument('Invalid log name, pick one from below:\n' + ', '.join(valid_logs))

            await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'modlog.{log_name}': channel_id}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_perm_level', 'set-perm-level'])
    async def setpermlevel(self, ctx, perm_level: int, *, role: discord.Role):
        """Sets a role's permission level"""
        if perm_level < 0:
            raise commands.BadArgument(f'{perm_level} is below 0')

        await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'perm_levels.{role.id}': perm_level}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_prefix', 'set-prefix'])
    async def setprefix(self, ctx, new_prefix):
        """Sets the guild prefix"""
        await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {'prefix': new_prefix}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_offset', 'set-offset'])
    async def setoffset(self, ctx, offset: int):
        """Sets the time offset from UTC"""
        if not -12 < offset < 14:
            raise commands.BadArgument(f'{offset} has to be between -12 and 14.')

        await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {'time_offset': offset}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_detection', 'set-detection'])
    async def setdetection(self, ctx, detection_type: lower, value):
        """Sets or toggle the auto moderation types

        Valid types: block_invite, mention_limit, spam_detection
        """
        if detection_type == 'block_invite':
            await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {'detections.block_invite': commands.core._convert_to_bool(value)}}, upsert=True)
            await ctx.send(self.bot.accept)
        elif detection_type in ('mention_limit', 'spam_detection'):
            try:
                if int(value) <= 0:
                    raise ValueError
                await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'detections.{detection_type}': int(value)}}, upsert=True)
            except ValueError as e:
                raise commands.BadArgument(f'{value} (`value`) is not a valid number above 0') from e
            await ctx.send(self.bot.accept)
        else:
            raise commands.BadArgument('Invalid log name, pick one from below:\nblock_invite, mention_limit, spam_detection')

    @command(10, aliases=['set-guild-whitelist', 'set_guild_whitelist'])
    async def setguildwhitelist(self, ctx, guild_id: int):
        """Adds a server to the whitelist.

        Invite detection will not trigger when this guild's invite is sent.
        The current server is always whitelisted.
        """
        await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$push': {'whitelisted_guilds': str(guild_id)}})
        await ctx.send(self.bot.accept)

    @group(8, name='filter', invoke_without_command=True)
    async def filter_(self, ctx):
        """Controls the word filter"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='filter')

    @filter_.command(8)
    async def add(self, ctx, *, word: lower):
        """Add blacklisted words into the word filter"""
        await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$push': {'detections.filters': word}}, upsert=True)
        await ctx.send(self.bot.accept)

    @filter_.command(8)
    async def remove(self, ctx, *, word: lower):
        """Removes blacklisted words from the word filter"""
        await self.bot.mongo.config.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$pull': {'detections.filters': word}}, upsert=True)
        await ctx.send(self.bot.accept)

    @filter_.command(7, name='list')
    async def list_(self, ctx):
        """Lists the full word filter"""
        guild_info = await self.bot.mongo.config.guilds.find_one({'guild_id': str(ctx.guild.id)})
        await ctx.send(f"Filters: {', '.join([f'`{i}`' for i in guild_info.get('detections', {}).get('filters', [])])}")


def setup(bot):
    bot.add_cog(Setup(bot))

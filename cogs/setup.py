import copy
import json

import discord
from discord.ext import commands
from discord.ext.commands import Cog

from ext.errors import BotMissingPermissionsInChannel
from ext.utils import get_command_level, lower, EmojiOrUnicode
from ext.command import command, group, RainGroup


class Setup(commands.Cog):
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
                'member_warn': None,
                'member_mute': None,
                'member_unmute': None,
                'member_kick': None,
                'member_ban': None,
                'member_unban': None,
                'member_softban': None,
                'message_purge': None,
                'channel_lockdown': None,
                'channel_slowmode': None
            },
            'time_offset': 0,
            'detections': {
                'filters': [],
                'block_invite': False,
                'mention_limit': None,
                'spam_detection': None,
                'repetitive_message': None
            },
            'giveaway': {
                'channel_id': None,
                'role_id': None,
                'emoji_id': None
            },
            'perm_levels': {},
            'command_levels': {},
            'warn_punishments': {},
            'notes': [],
            'warns': [],
            'mutes': [],
            'whitelisted_guilds': [],
            'mute_role': None,
            'prefix': '!!'
        }

    @Cog.listener()
    async def on_guild_join(self, guild):
        default = copy.copy(self.default)
        default['guild_id'] = str(guild.id)
        await self.bot.mongo.rainbot.guilds.insert_one(default)

    @command(6, aliases=['view_config', 'view-config'])
    async def viewconfig(self, ctx):
        """View the current guild configuration"""
        guild_info = await self.bot.mongo.rainbot.guilds.find_one({'guild_id': str(ctx.guild.id)}) or {'_id': None}
        del guild_info['_id']
        try:
            await ctx.send(f'```json\n{json.dumps(guild_info, indent=2)}\n```')
        except discord.HTTPException:
            async with self.bot.session.post('https://hasteb.in/documents', data=json.dumps(guild_info, indent=4)) as resp:
                data = await resp.json()
                await ctx.send(f"Your server's current configuration: https://hasteb.in/{data['key']}")

    @command(10, aliases=['import_config', 'import-config'])
    async def importconfig(self, ctx, *, url):
        """Imports a new guild configuration.

        Generate one from https://fourjr.github.io/rainbot/"""
        if url.startswith('http'):
            if url.startswith('https://hasteb.in') and 'raw' not in url:
                url = 'https://hasteb.in/raw/' + url[18:]

            async with self.bot.session.get(url) as resp:
                data = await resp.json(content_type=None)
        else:
            data = url
        data['guild_id'] = str(ctx.guild.id)
        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': data}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['reset_config', 'reset-config'])
    async def resetconfig(self, ctx):
        """Resets configuration to default"""
        await ctx.invoke(self.viewconfig)
        data = copy.copy(self.default)
        data['guild_id'] = str(ctx.guild.id)
        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': data}, upsert=True)
        await ctx.send('All configuration reset')

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
                await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'logs.{i}': channel_id}}, upsert=True)
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument('Invalid log name, pick one from below:\n' + ', '.join(valid_logs))

            await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'logs.{log_name}': channel_id}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, alises=['set_modlog', 'set-modlog'])
    async def setmodlog(self, ctx, log_name: lower, channel: discord.TextChannel=None):
        """Sets the log channel for various types of logging

        Valid types: all, member_warn, member_mute, member_unmute, member_kick, member_ban, member_unban, member_softban, message_purge, channel_lockdown, channel_slowmode
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
                await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'modlog.{i}': channel_id}}, upsert=True)
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument('Invalid log name, pick one from below:\n' + ', '.join(valid_logs))

            await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'modlog.{log_name}': channel_id}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_perm_level', 'set-perm-level'])
    async def setpermlevel(self, ctx, perm_level: int, *, role: discord.Role):
        """Sets a role's permission level"""
        if perm_level < 0:
            raise commands.BadArgument(f'{perm_level} is below 0')

        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'perm_levels.{role.id}': perm_level}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_command_level', 'set-command-level'])
    async def setcommandlevel(self, ctx, perm_level: int, *, command: lower):
        """Changes a command's required permission level"""
        if perm_level < 0:
            raise commands.BadArgument(f'{perm_level} is below 0')

        cmd = self.bot.get_command(command)
        if not cmd:
            raise commands.BadArgument(f'No command with name "{command}" found')

        if isinstance(cmd, RainGroup):
            raise commands.BadArgument('Cannot override a command group')

        name = cmd.qualified_name.replace(' ', '_')
        levels = {f'command_levels.{name}': perm_level}
        
        if cmd.parent:
            guild_info = await ctx.guild_config()
            parent_level = get_command_level(cmd.parent, guild_info)
            if perm_level < parent_level:
                levels[f'command_levels.{cmd.parent.name}'] = perm_level
            elif perm_level > parent_level:
                cmd_level = get_command_level(cmd, guild_info)
                all_levels = [get_command_level(c, guild_info) for c in cmd.parent.commands]

                all_levels.remove(cmd_level)
                all_levels.append(perm_level)

                lowest = min(all_levels)
                if lowest > parent_level:
                    levels[f'command_levels.{cmd.parent.name}'] = lowest

        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': levels}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_prefix', 'set-prefix'])
    async def setprefix(self, ctx, new_prefix):
        """Sets the guild prefix"""
        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {'prefix': new_prefix}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_offset', 'set-offset'])
    async def setoffset(self, ctx, offset: int):
        """Sets the time offset from UTC"""
        if not -12 < offset < 14:
            raise commands.BadArgument(f'{offset} has to be between -12 and 14.')

        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {'time_offset': offset}}, upsert=True)
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_detection', 'set-detection'])
    async def setdetection(self, ctx, detection_type: lower, value):
        """Sets or toggle the auto moderation types

        Valid types: block_invite, mention_limit, spam_detection, repetitive_message
        """
        if detection_type == 'block_invite':
            await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {'detections.block_invite': commands.core._convert_to_bool(value)}}, upsert=True)
            await ctx.send(self.bot.accept)
        elif detection_type in ('mention_limit', 'spam_detection', 'repetitive_message'):
            try:
                if int(value) <= 0:
                    raise ValueError
                await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'detections.{detection_type}': int(value)}}, upsert=True)
            except ValueError as e:
                raise commands.BadArgument(f'{value} (`value`) is not a valid number above 0') from e
            await ctx.send(self.bot.accept)
        else:
            raise commands.BadArgument('Invalid log name, pick one from below:\nblock_invite, mention_limit, spam_detection, repetitive_message')

    @command(10, aliases=['set-guild-whitelist', 'set_guild_whitelist'])
    async def setguildwhitelist(self, ctx, guild_id: int=None):
        """Adds a server to the whitelist.

        Invite detection will not trigger when this guild's invite is sent.
        The current server is always whitelisted.

        Run without arguments to clear whitelist
        """
        if guild_id is None:
            await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$unset': {'whitelisted_guilds': ""}}, upsert=True)

        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$push': {'whitelisted_guilds': str(guild_id)}})
        await ctx.send(self.bot.accept)

    @group(8, name='filter', invoke_without_command=True)
    async def filter_(self, ctx):
        """Controls the word filter"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='filter')

    @filter_.command(8)
    async def add(self, ctx, *, word: lower):
        """Add blacklisted words into the word filter"""
        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$push': {'detections.filters': word}}, upsert=True)
        await ctx.send(self.bot.accept)

    @filter_.command(8)
    async def remove(self, ctx, *, word: lower):
        """Removes blacklisted words from the word filter"""
        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$pull': {'detections.filters': word}}, upsert=True)
        await ctx.send(self.bot.accept)

    @filter_.command(8, name='list')
    async def list_(self, ctx):
        """Lists the full word filter"""
        guild_info = await self.bot.mongo.rainbot.guilds.find_one({'guild_id': str(ctx.guild.id)})
        await ctx.send(f"Filters: {', '.join([f'`{i}`' for i in guild_info.get('detections', {}).get('filters', [])])}")

    @command(10, aliases=['set-warn-punishment', 'set_warn_punishment'])
    async def setwarnpunishment(self, ctx, limit: int, punishment=None):
        """Sets punishment after certain number of warns.
        Punishments can be "kick", "ban" or "none".

        Example: !!setwarnpunishment 5 kick

        It is highly encouraged to add a final "ban" condition
        """
        if punishment not in ('kick', 'ban', 'none'):
            raise commands.BadArgument('Invalid punishment, pick from `kick`, `ban`, `none`.')

        if punishment == 'none' or punishment is None:
            await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$unset': {f'warn_punishments.{limit}': ''}}, upsert=True)
        else:
            await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {f'warn_punishments.{limit}': punishment}}, upsert=True)

        await ctx.send(self.bot.accept)

    @command(10, aliases=['set-giveaway' 'set_giveaway'])
    async def setgiveaway(self, ctx, emoji: EmojiOrUnicode, channel: discord.TextChannel, role=None):
        """Sets up giveaways. Role can be @everyone, @here or none"""
        if role == 'none' or role is None:
            role_id = None
        elif role in ('@everyone', '@here'):
            role_id = role
        else:
            role_id = (await commands.RoleConverter().convert(ctx, role)).id

        await self.bot.mongo.rainbot.guilds.find_one_and_update({'guild_id': str(ctx.guild.id)}, {'$set': {
            'giveaway.emoji_id': emoji.id,
            'giveaway.channel_id': channel.id,
            'giveaway.role_id': role_id
        }}, upsert=True)

        await ctx.send(self.bot.accept)


def setup(bot):
    bot.add_cog(Setup(bot))

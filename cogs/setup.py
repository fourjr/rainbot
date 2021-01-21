import copy
from ext.time import UserFriendlyTime
import io
import json
import re
from typing import Any, Dict, List, Union

import discord
from discord.ext import commands
from discord.ext.commands import Cog
from imagehash import average_hash
from PIL import Image

from bot import rainbot
from ext.errors import BotMissingPermissionsInChannel
from ext.utility import get_command_level, lower
from ext.command import command, group, RainGroup
from ext.database import DEFAULT, RECOMMENDED_DETECTIONS


class Setup(commands.Cog):
    """Setting up rainbot: https://github.com/fourjr/rainbot/wiki/Setting-up-rainbot"""

    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.order = 1

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.bot.db.create_new_config(guild.id)

    @command(6, aliases=['view_config', 'view-config'])
    async def viewconfig(self, ctx: commands.Context, options: lower=None) -> None:
        """View the current guild configuration

        options can be "all" to include mutes and warns
        """
        guild_config = copy.copy(await self.bot.db.get_guild_config(ctx.guild.id))
        del guild_config['_id']

        if options != 'all':
            del guild_config['warns']
            del guild_config['mutes']

        try:
            await ctx.send(f'```json\n{json.dumps(guild_config, indent=2)}\n```')
        except discord.HTTPException:
            async with self.bot.session.post('https://hastebin.cc/documents', data=json.dumps(guild_config, indent=4)) as resp:
                data = await resp.json()
                await ctx.send(f"Your server's current configuration: https://hastebin.cc/{data['key']}")

    @command(10, aliases=['import_config', 'import-config'])
    async def importconfig(self, ctx: commands.Context, *, url: str) -> None:
        """Imports a new guild configuration.

        Generate one from https://fourjr.github.io/rainbot/"""
        if url.startswith('http'):
            if url.startswith('https://hastebin.cc') and 'raw' not in url:
                url = 'https://hastebin.cc/raw/' + url[18:]

            async with self.bot.session.get(url) as resp:
                try:
                    data = await resp.json(content_type=None)
                except json.JSONDecodeError as e:
                    return await ctx.send(f'Error decoding JSON: {e}')
        else:
            data = url
        data['guild_id'] = str(ctx.guild.id)
        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': data})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['reset_config', 'reset-config'])
    async def resetconfig(self, ctx: commands.Context):
        """Resets configuration to default"""
        await ctx.invoke(self.viewconfig)
        data = copy.copy(DEFAULT)
        data['guild_id'] = str(ctx.guild.id)
        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': data})
        await ctx.send('All configuration reset')

    @command(10, alises=['set_log', 'set-log'])
    async def setlog(self, ctx: commands.Context, log_name: lower, channel: discord.TextChannel=None) -> None:
        """Sets the log channel for various types of logging

        Valid types: all, message_delete, message_edit, member_join, member_remove, member_ban, member_unban, vc_state_change, channel_create, channel_delete, role_create, role_delete
        """
        valid_logs = DEFAULT['logs'].keys()
        channel_id = None
        if channel:
            try:
                await channel.send('Testing the logs')
            except discord.Forbidden:
                raise BotMissingPermissionsInChannel(['send_messages'], channel)
            channel_id = str(channel.id)

        if log_name == 'all':
            for i in valid_logs:
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'logs.{i}': channel_id}})
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument('Invalid log name, pick one from below:\n' + ', '.join(valid_logs))

            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'logs.{log_name}': channel_id}})
        await ctx.send(self.bot.accept)

    @command(10, alises=['set_modlog', 'set-modlog'])
    async def setmodlog(self, ctx: commands.Context, log_name: lower, channel: discord.TextChannel=None) -> None:
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

        valid_logs = DEFAULT['modlog'].keys()
        if log_name == 'all':
            for i in valid_logs:
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'modlog.{i}': channel_id}})
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument('Invalid log name, pick one from below:\n' + ', '.join(valid_logs))

            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'modlog.{log_name}': channel_id}})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_perm_level', 'set-perm-level'])
    async def setpermlevel(self, ctx: commands.Context, perm_level: int, *, role: discord.Role) -> None:
        """Sets a role's permission level"""
        if perm_level < 0:
            raise commands.BadArgument(f'{perm_level} is below 0')

        if perm_level == 0:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'perm_levels': {'role_id': str(role.id)}}})
        else:
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            if str(role.id) in [i['role_id'] for i in guild_config['perm_levels']]:
                # overwrite
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'perm_levels.$[elem].level': perm_level}}, array_filters=[{'elem.role_id': str(role.id)}])
            else:
                # push
                await self.bot.db.update_guild_config(ctx.guild.id, {'$push': {'perm_levels': {'role_id': str(role.id), 'level': perm_level}}})

        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_command_level', 'set-command-level'])
    async def setcommandlevel(self, ctx: commands.Context, perm_level: Union[int, str], *, command: lower) -> None:
        """Changes a command's required permission level

        Examples:
        - !!setcommandlevel reset ban
        - !!setcommandlevel 8 warn add
        """
        if isinstance(perm_level, int) and (perm_level < 0 or perm_level > 15):
            raise commands.BadArgument(f'{perm_level} is an invalid level, valid levels: 0-15 or reset')

        if isinstance(perm_level, str) and perm_level != 'reset':
            raise commands.BadArgument(f'{perm_level} is an invalid level, valid levels: 0-15 or reset')

        cmd = self.bot.get_command(command)
        if not cmd:
            raise commands.BadArgument(f'No command with name "{command}" found')

        if isinstance(cmd, RainGroup):
            raise commands.BadArgument('Cannot override a command group')

        name = cmd.qualified_name

        if perm_level == 'reset':
            int_perm_level = cmd.perm_level
        else:
            int_perm_level = perm_level

        levels: Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]] = [{'command': name, 'level': int_perm_level}]
        action = "pull" if int_perm_level == cmd.perm_level else "push"
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)

        if cmd.parent:
            parent_level = get_command_level(cmd.parent, guild_config)
            if int_perm_level < parent_level:
                levels.append({'command': cmd.parent.name, 'level': int_perm_level})
            elif int_perm_level > parent_level:
                cmd_level = get_command_level(cmd, guild_config)
                all_levels = [get_command_level(c, guild_config) for c in cmd.parent.commands]

                all_levels.remove(cmd_level)
                all_levels.append(int_perm_level)

                lowest = min(all_levels)
                if lowest > parent_level:
                    levels.append({'command': cmd.parent.name, 'level': lowest})

        to_push_levels = {'$each': copy.deepcopy(levels)}

        print(levels)
        for i in levels:
            i['level'] = get_command_level(self.bot.get_command(i['command']), guild_config)
            i['command'] = i['command'].replace(' ', '_')

        levels = {'$in': levels}
        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'command_levels': levels}})

        if action == 'push':
            await self.bot.db.update_guild_config(ctx.guild.id, {'$push': {'command_levels': to_push_levels}})

        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_prefix', 'set-prefix'])
    async def setprefix(self, ctx: commands.Context, new_prefix: str) -> None:
        """Sets the guild prefix"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'prefix': new_prefix}})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_offset', 'set-offset'])
    async def setoffset(self, ctx: commands.Context, offset: int) -> None:
        """Sets the time offset from UTC"""
        if not -12 < offset < 14:
            raise commands.BadArgument(f'{offset} has to be between -12 and 14.')

        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'time_offset': offset}})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_detection', 'set-detection'])
    async def setdetection(self, ctx: commands.Context, detection_type: lower, value: str) -> None:
        """Sets or toggle the auto moderation types

        Valid types: block_invite, english_only, mention_limit, spam_detection, repetitive_message, auto_purge_trickocord, max_lines, max_words, max_characters, caps_message_percent, caps_message_min_words
        """
        if detection_type in ('block_invite', 'english_only', 'auto_purge_trickocord'):
            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'detections.{detection_type}': commands.core._convert_to_bool(value)}})
            await ctx.send(self.bot.accept)
        elif detection_type in ('mention_limit', 'spam_detection', 'repetitive_message', 'max_lines', 'max_words', 'max_characters', 'caps_message_percent', 'caps_message_min_words'):
            # int or float
            try:
                value = float(value)
                if value <= 0:
                    raise ValueError
            except ValueError:
                try:
                    value = int(value)
                    if value <= 0:
                        raise ValueError
                except ValueError as e:
                    raise commands.BadArgument(f'{value} (value) is not a valid number above 0') from e

            if detection_type in ('caps_message_percent'):
                if value > 1:
                    raise commands.BadArgument(f'{value} (value) should be between 1 and 0 as it is a percent.')

            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'detections.{detection_type}': int(value)}})
            await ctx.send(self.bot.accept)
        else:
            raise commands.BadArgument('Invalid detection.')

    @command(10, aliases=['set-alert', 'set_alert'])
    async def setalert(self, ctx: commands.Context, punishment: lower, *, value: str=None) -> None:
        """Set the message DM-ed to the user upon a punishment.

        Possible punishments: kick, ban, mute, softban, unmute

        Possible templates:
        - `{time}` (in time offset)
        - `{author}`
        - `{user}`
        - `{reason}` (will be "None" if not provided)
        - `{channel}`
        - `{guild}`
        - `{duration}` (for mute only)

        Leave value blank to remove

        Example: !!setalert mute You have been muted in {guild.name} for {reason} for a duration of {duration}!
        """
        valid_punishments = ('kick', 'ban', 'mute', 'softban', 'unmute')

        if punishment in valid_punishments:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'alert.{punishment}': value}})
        else:
            raise commands.BadArgument(f'Invalid punishment. Pick from {", ".join(valid_punishments)}.')
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_detection_punishments', 'set-detection-punishments'])
    async def setdetectionpunishments(self, ctx: commands.Context, detection_type: lower, key: lower, *, value: lower) -> None:
        """Sets punishment for the detections

        Valid detections: filters, regex_filters, block_invite, english_only, mention_limit, spam_detection, repetitive_message, sexually_explicit, auto_purge_trickocord, max_lines, max_words, max_characters, caps_message

        Valid keys: warn, mute, kick, ban, delete

        Warn accepts a number of warns to give to the user
        Kick, ban and delete accepts "yes/no"
        Mute has to be set to a time, or none (mute indefinitely).

        Examples:
        - `!!setdetectionpunishments filters warn 1`
        - `!!setdetectionpunishments block_invite kick yes`
        - `!!setdetectionpunishments mention_limit mute 1d`
        """
        valid_detections = list(DEFAULT['detection_punishments'].keys())

        if detection_type not in valid_detections:
            raise commands.BadArgument('Invalid detection.')

        valid_keys = list(DEFAULT['detection_punishments'][valid_detections[0]].keys())

        if key not in valid_keys:
            raise commands.BadArgument('Invalid key, pick one from below:\n' + ', '.join(valid_keys))

        if key in ('warn'):
            try:
                value = int(value)
            except ValueError:
                raise commands.BadArgument(f'{key} accepts a number')

        elif key in ('kick', 'ban', 'delete'):
            value = commands.core._convert_to_bool(value)

        elif key in ('mute'):
            if value == 'none':
                value = None
            else:
                await UserFriendlyTime(default='nil').convert(ctx, value)  # validation

        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'detection_punishments.{detection_type}.{key}': value}})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_recommended', 'set-recommended'])
    async def setrecommended(self, ctx: commands.Context) -> None:
        """Sets a recommended set of detections"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': RECOMMENDED_DETECTIONS})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set-guild-whitelist', 'set_guild_whitelist'])
    async def setguildwhitelist(self, ctx: commands.Context, guild_id: int=None) -> None:
        """Adds a server to the whitelist.

        Invite detection will not trigger when this guild's invite is sent.
        The current server is always whitelisted.

        Run without arguments to clear whitelist
        """
        if guild_id is None:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'whitelisted_guilds': []}})
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {'whitelisted_guilds': str(guild_id)}})

        await ctx.send(self.bot.accept)

    @command(10, aliases=['set-detection-ignore', 'set_detection_ignore'])
    async def setdetectionignore(self, ctx: commands.Context, detection_type: lower, channel: discord.TextChannel=None) -> None:
        """Ignores detections in specified channels

        Valid detections: all, filters, regex_filters, block_invite, english_only, mention_limit, spam_detection, repetitive_message, sexually_explicit, auto_purge_trickocord, max_lines, max_words, max_characters, caps_message
        Run without specifying channel to clear ignored channels
        """
        valid_detections = list(DEFAULT['ignored_channels'].keys())

        if detection_type not in valid_detections + ["all"]:
            raise commands.BadArgument('Invalid detection, pick one from below:\n all, ' + ', '.join(valid_detections))

        if detection_type == 'all':
            for i in valid_detections:
                if channel is None:
                    await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'ignored_channels.{i}': []}})
                else:
                    await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {f'ignored_channels.{i}': str(channel.id)}})
        else:
            if channel is None:
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'ignored_channels.{detection_type}': []}})
            else:
                await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {f'ignored_channels.{detection_type}': str(channel.id)}})

        await ctx.send(self.bot.accept)

    @group(8, invoke_without_command=True)
    async def regexfilter(self, ctx: commands.Context) -> None:
        """Controls the regex filter"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='regexfilter')

    @regexfilter.command(8, name='add')
    async def re_add(self, ctx: commands.Context, *, pattern) -> None:
        """Add blacklisted regex into the regex filter"""
        try:
            re.compile(pattern)
        except re.error as e:
            return await ctx.send(f'Invalid regex pattern: `{e}`.\nView <https://regexr.com/> for a guide.')

        await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {'detections.regex_filters': pattern}})
        await ctx.send(self.bot.accept)

    @regexfilter.command(8, name='remove')
    async def re_remove(self, ctx: commands.Context, *, pattern) -> None:
        """Removes blacklisted regex from the regex filter"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'detections.regex_filters': pattern}})
        await ctx.send(self.bot.accept)

    @regexfilter.command(8, name='list')
    async def re_list_(self, ctx: commands.Context) -> None:
        """Lists the full word filter"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        await ctx.send(f"Regex Filters: {', '.join([f'`{i}`' for i in guild_config.detections.regex_filters])}")

    @group(8, name='filter', invoke_without_command=True)
    async def filter_(self, ctx: commands.Context) -> None:
        """Controls the word filter"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='filter')

    @filter_.command(8)
    async def add(self, ctx: commands.Context, *, word: lower=None) -> None:
        """Add blacklisted words into the word filter

        Can also add image filters if an iamge is attached,
        do note that it can easily be bypassed by
        slightly editing the images."""
        if word:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {'detections.filters': word}})
        else:
            to_add = []
            for i in ctx.message.attachments:
                if i.filename.lower().endswith('.png') or i.filename.lower().endswith('.jpg') or i.filename.lower().endswith('.jpeg'):
                    stream = io.BytesIO()
                    await i.save(stream)
                    img = Image.open(stream)
                    image_hash = str(average_hash(img))
                    img.close()

                    to_add.append(image_hash)

            if to_add:
                await self.bot.db.update_guild_config(ctx.guild.id, {'$addToSet': {'detections.image_filters': {'$each': to_add}}})
            else:
                raise commands.UserInputError('word has to be provided or an image has to be attached.')

        await ctx.send(self.bot.accept)

    @filter_.command(8)
    async def remove(self, ctx: commands.Context, *, word: lower=None) -> None:
        """Removes blacklisted words from the word filter

        Can also remove image filters if an iamge is attached, """
        if word:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'detections.filters': word}})
        else:
            to_remove = []
            for i in ctx.message.attachments:
                if i.filename.lower().endswith('.png') or i.filename.lower().endswith('.jpg') or i.filename.lower().endswith('.jpeg'):
                    stream = io.BytesIO()
                    await i.save(stream)
                    img = Image.open(stream)
                    image_hash = str(average_hash(img))
                    img.close()

                    to_remove.append(image_hash)

            if to_remove:
                await self.bot.db.update_guild_config(ctx.guild.id, {'$pullAll': {'detections.image_filters': to_remove}})
            else:
                raise commands.UserInputError('word has to be provided or an image has to be attached.')

        await ctx.send(self.bot.accept)

    @filter_.command(8, name='list')
    async def list_(self, ctx: commands.Context) -> None:
        """Lists the full word filter"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        await ctx.send(f"Filters: {', '.join([f'`{i}`' for i in guild_config.detections.filters])}")

    @command(10, aliases=['set-warn-punishment', 'set_warn_punishment'])
    async def setwarnpunishment(self, ctx: commands.Context, limit: int, punishment=None) -> None:
        """Sets punishment after certain number of warns.
        Punishments can be "kick", "ban" or "none".

        Example: !!setwarnpunishment 5 kick

        It is highly encouraged to add a final "ban" condition
        """
        if punishment not in ('kick', 'ban', 'none'):
            raise commands.BadArgument('Invalid punishment, pick from `kick`, `ban`, `none`.')

        if punishment == 'none' or punishment is None:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'warn_punishments': {'warn_number': limit}}})
        else:
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            if limit in [i['warn_number'] for i in guild_config['warn_punishments']]:
                # overwrite
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'warn_punishments.$[elem].punishment': punishment}}, array_filters=[{'elem.warn_number': limit}])
            else:
                # push
                await self.bot.db.update_guild_config(ctx.guild.id, {'$push': {'warn_punishments': {'warn_number': limit, 'punishment': punishment}}})

        await ctx.send(self.bot.accept)

    @command(10, aliases=['set-explicit', 'set_explicit'], usage='[types...]')
    async def setexplicit(self, ctx: commands.Context, *types_) -> None:
        """Types can be a space-seperated list of the following:
        `EXPOSED_ANUS, EXPOSED_ARMPITS, COVERED_BELLY, EXPOSED_BELLY, COVERED_BUTTOCKS, EXPOSED_BUTTOCKS, FACE_F, FACE_M, COVERED_FEET, EXPOSED_FEET, COVERED_BREAST_F, EXPOSED_BREAST_F, COVERED_GENITALIA_F, EXPOSED_GENITALIA_F, EXPOSED_BREAST_M, EXPOSED_GENITALIA_M`
        """
        possibles = ['EXPOSED_ANUS', 'EXPOSED_ARMPITS', 'COVERED_BELLY', 'EXPOSED_BELLY', 'COVERED_BUTTOCKS', 'EXPOSED_BUTTOCKS', 'FACE_F', 'FACE_M', 'COVERED_FEET', 'EXPOSED_FEET', 'COVERED_BREAST_F', 'EXPOSED_BREAST_F', 'COVERED_GENITALIA_F', 'EXPOSED_GENITALIA_F', 'EXPOSED_BREAST_M', 'EXPOSED_GENITALIA_M']
        for i in types_:
            if i not in possibles:
                return await ctx.send(f'{i} is not a valid type')
        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'detections.sexually_explicit': types_}})

        await ctx.send(self.bot.accept)


def setup(bot: rainbot) -> None:
    bot.add_cog(Setup(bot))

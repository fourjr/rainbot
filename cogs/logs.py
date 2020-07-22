from datetime import datetime, timedelta

import discord
from discord.ext import commands
from discord.ext.commands import Cog


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.fill_message_cache())

    async def fill_message_cache(self):
        await self.bot.wait_until_ready()

        after = datetime.now()
        after -= timedelta(minutes=15)

        for i in self.bot.get_all_channels():
            if isinstance(i, discord.TextChannel):
                try:
                    self.bot._connection._messages += await i.history(limit=30, after=after).flatten()
                except discord.Forbidden:
                    pass

    async def check_enabled(self, guild_id, item):
        data = await self.bot.db.get_guild_config(guild_id)
        try:
            return self.bot.get_channel(int(data.logs.get(item, 0)))
        except (ValueError, TypeError):
            return data.get(item, False)

    async def send_log(self, log, payload, raw: bool, end: str=None, *, mode: str=None, extra=None):
        current_time = datetime.utcnow()
        try:
            guild_id = payload.guild.id
        except AttributeError:
            try:
                guild_id = payload.guild_id
            except AttributeError:
                guild_id = payload.data.get('guild_id')

        guild_config = await self.bot.db.get_guild_config(guild_id)
        current_time += timedelta(hours=guild_config.time_offset)
        current_time = current_time.strftime('%H:%M:%S')

        if raw:
            await log.send(f"`{current_time}` Message ({payload.message_id}) has been {end}.")
        else:
            if mode == 'message_delete':
                await log.send(f"`{current_time}` {payload.author} ({payload.author.id}): Message ({payload.id}) has been deleted in **#{payload.channel.name}** ({payload.channel.id})\n```\n{payload.content}\n```")
            elif mode == 'member_join':
                await log.send(f"`{current_time}` {payload} ({payload.id}) has joined.")
            elif mode == 'member_remove':
                await log.send(f"`{current_time}` {payload} ({payload.id}) has left the server.")
            elif mode == 'message_edit':
                await log.send(f"`{current_time}` {payload.author} ({payload.author.id}): Message ({payload.id}) has been edited in **#{payload.channel.name}** ({payload.channel.id})\nB:```\n{payload.content}\n```\nA:\n```{extra.content}\n```")
            elif mode == 'member_leave_vc':
                await log.send(f"`{current_time}` {payload} ({payload.id}) has left :microphone: **{extra}** ({extra.id}).")
            elif mode == 'member_join_vc':
                await log.send(f"`{current_time}` {payload} ({payload.id}) has joined :microphone: **{extra}** ({extra.id}).")
            elif mode == 'member_deaf_vc':
                await log.send(f"`{current_time}` {payload} ({payload.id}) is{'' if extra else ' not'} deafened")
            elif mode == 'member_mute_vc':
                await log.send(f"`{current_time}` {payload} ({payload.id}) is{'' if extra else ' not'} muted")
            elif mode == 'channel_role_create':
                await log.send(f"`{current_time}` {extra} **{payload}** ({payload.id}) is created")
            elif mode == 'channel_role_delete':
                await log.send(f"`{current_time}` {extra} **{payload}** ({payload.id}) is deleted")
            else:
                raise NotImplementedError(f'{mode} not implemented')

    @Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(message.guild.id, 'message_delete')
        if not log_channel:
            return
        await self.send_log(log_channel, message, False, mode='message_delete')

    @Cog.listener()
    async def on_raw_message_delete(self, payload):
        log_channel = await self.check_enabled(payload.guild_id, 'message_delete')
        if not payload.guild_id or not log_channel or self.bot.dev_mode:
            return
        await self.send_log(log_channel, payload, True, 'deleted')

    @Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(before.guild.id, 'message_edit')
        if not log_channel:
            return
        await self.send_log(log_channel, before, False, mode='message_edit', extra=after)

    @Cog.listener()
    async def on_raw_message_edit(self, payload):
        log_channel = await self.check_enabled(payload.data.get('guild_id'), 'message_edit')
        if not payload.data.get('guild_id') or not log_channel or self.bot.dev_mode:
            return

        try:
            await self.send_log(log_channel, payload, True, f"updated: ```\n{payload.data['content']}\n```")
        except KeyError:
            pass

    @Cog.listener()
    async def on_raw_message_individual_delete(self, payload):
        log_channel = await self.check_enabled(payload.guild_id, 'message_delete')
        if not payload.guild_id or not log_channel or self.bot.dev_mode:
            return
        await self.send_log(log_channel, payload, True, 'deleted')

    @Cog.listener()
    async def on_member_join(self, member):
        if not member.guild or member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, 'member_join')
        if not log_channel:
            return
        await self.send_log(log_channel, member, False, mode='member_join')

    @Cog.listener()
    async def on_member_remove(self, member):
        if not member.guild or member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, 'member_remove')
        if not log_channel:
            return
        await self.send_log(log_channel, member, False, mode='member_remove')

    @Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, 'vc_state_change')
        if before.channel != after.channel:
            if not log_channel:
                return
            if before.channel:
                await self.send_log(log_channel, member, False, mode='member_leave_vc', extra=before.channel)
            if after.channel:
                await self.send_log(log_channel, member, False, mode='member_join_vc', extra=after.channel)
        if before.deaf != after.deaf:
            await self.send_log(log_channel, member, False, mode='member_deaf_vc', extra=after.deaf)
        if before.mute != after.mute:
            await self.send_log(log_channel, member, False, mode='member_mute_vc', extra=after.mute)

    @Cog.listener()
    async def on_guild_channel_create(self, channel):
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(channel.guild.id, 'channel_create')
        if log_channel:
            await self.send_log(log_channel, channel, False, mode='channel_role_create', extra='Channel')

        # Setup mute role perms
        guild_config = await self.bot.db.get_guild_config(channel.guild.id)
        if guild_config.mute_role:
            role = discord.utils.get(channel.guild.roles, id=int(guild_config['mute_role']))
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel)):
                try:
                    await channel.set_permissions(role, send_messages=False, speak=False)
                except discord.NotFound:
                    pass

    @Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(channel.guild.id, 'channel_delete')
        if log_channel:
            await self.send_log(log_channel, channel, False, mode='channel_role_delete', extra='Channel')

    @Cog.listener()
    async def on_guild_role_create(self, role):
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(role.guild.id, 'role_create')
        if log_channel:
            await self.send_log(log_channel, role, False, mode='channel_role_create', extra='Role')

    @Cog.listener()
    async def on_guild_role_delete(self, role):
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(role.guild.id, 'role_delete')
        if log_channel:
            await self.send_log(log_channel, role, False, mode='channel_role_delete', extra='Role')


def setup(bot):
    bot.add_cog(Logging(bot))

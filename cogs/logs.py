from datetime import datetime, timedelta
from typing import Any, List, Union

import discord
from discord.ext import commands
from discord.ext.commands import Cog

from bot import rainbot
from ext.utility import QuickId, format_timedelta


class Logging(commands.Cog):
    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.bot.loop.create_task(self.fill_message_cache())

    async def fill_message_cache(self) -> None:
        await self.bot.wait_until_ready()

        after = datetime.utcnow()
        after -= timedelta(minutes=30)

        for i in self.bot.get_all_channels():
            if isinstance(i, discord.TextChannel):
                try:
                    messages = await i.history(limit=30, after=after).flatten()
                except discord.Forbidden:
                    pass
                else:
                    if not messages:
                        messages = await i.history(limit=5).flatten()  # get 5 messages if no messages are recent
                    self.bot._connection._messages += messages

    async def check_enabled(self, guild_id: int, item: Any):
        data = await self.bot.db.get_guild_config(guild_id)
        try:
            return self.bot.get_channel(int(data.logs.get(item, 0)))
        except (ValueError, TypeError):
            return data.get(item, False)

    async def send_log(
        self,
        log: discord.TextChannel,
        payload: Union[discord.Message, discord.User, discord.TextChannel, discord.VoiceChannel, discord.Role, discord.Member, int, discord.RawMessageDeleteEvent],
        raw: bool, end: str=None, *, mode: str=None,
        extra: Union[discord.Message, bool, discord.VoiceChannel, str]=None
    ) -> None:
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
            if mode == 'bulk':
                await log.send(f"`{current_time}` Message ({payload.id}) has been {end}.")
            else:
                await log.send(f"`{current_time}` Message ({payload.message_id}) has been {end}.")
        else:
            if mode == 'message_delete':
                try:
                    await log.send(f"`{current_time}` {payload.author} ({payload.author.id}): Message ({payload.id}) has been deleted in **#{payload.channel.name}** ({payload.channel.id})\n```\n{payload.content}\n```")
                except discord.HTTPException:
                    # TODO: to implement a more elegant solution
                    await log.send(f"`{current_time}` {payload.author} ({payload.author.id}): Message ({payload.id}) has been deleted in **#{payload.channel.name}** ({payload.channel.id})")
                    await log.send(f"```{payload.content}\n```")
            elif mode == 'member_join':
                fmt = f"`{current_time}` {payload} ({payload.id}) has joined. "
                delta = datetime.utcnow() - payload.created_at
                if delta.total_seconds() < 60 * 60 * 24:
                    # joined in last day
                    fmt += f"Warning: account created {format_timedelta(delta)} ago"
                await log.send(fmt)
            elif mode == 'member_remove':
                await log.send(f"`{current_time}` {payload} ({payload.id}) has left the server.")
            elif mode == 'message_edit':
                try:
                    await log.send(f"`{current_time}` {payload.author} ({payload.author.id}): Message ({payload.id}) has been edited in **#{payload.channel.name}** ({payload.channel.id})\nB:```\n{payload.content}\n```\nA:\n```{extra.content}\n```")
                except discord.HTTPException:
                    # to implement a more elegant solution
                    await log.send(f"`{current_time}` {payload.author} ({payload.author.id}): Message ({payload.id}) has been edited in **#{payload.channel.name}** ({payload.channel.id})")
                    await log.send(f"B:```\n{payload.content}\n```\n")
                    await log.send(f"A:\n```{extra.content}\n```")
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
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(message.guild.id, 'message_delete')
        if not log_channel:
            return
        await self.send_log(log_channel, message, False, mode='message_delete')

    @Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if not payload.cached_message:
            log_channel = await self.check_enabled(payload.guild_id, 'message_delete')
            if not payload.guild_id or not log_channel or self.bot.dev_mode:
                return
            await self.send_log(log_channel, payload, True, 'deleted')

    @Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.author.bot or before.content == after.content or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(before.guild.id, 'message_edit')
        if not log_channel:
            return
        await self.send_log(log_channel, before, False, mode='message_edit', extra=after)

    @Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if not payload.cached_message:
            log_channel = await self.check_enabled(payload.data.get('guild_id'), 'message_edit')
            if not payload.data.get('guild_id') or not log_channel or self.bot.dev_mode:
                return

            try:
                await self.send_log(log_channel, payload, True, f"updated: ```\n{payload.data['content']}\n```")
            except KeyError:
                pass

    @Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        log_channel = await self.check_enabled(payload.guild_id, 'message_delete')
        if not payload.guild_id or not log_channel or self.bot.dev_mode:
            return

        found = [i.id for i in payload.cached_messages]
        for id_ in payload.message_ids:
            if id_ not in found:
                await self.send_log(log_channel, QuickId(payload.guild_id, id_), True, 'deleted', mode='bulk')

    @Cog.listener()
    async def on_bulk_message_delete(self, payload: List[discord.Message]) -> None:
        guild_id = payload[0].guild.id
        log_channel = await self.check_enabled(guild_id, 'message_delete')
        if not guild_id or not log_channel or self.bot.dev_mode:
            return

        for message in payload:
            await self.send_log(log_channel, message, False, mode='message_delete')

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not member.guild or member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, 'member_join')
        if not log_channel:
            return
        await self.send_log(log_channel, member, False, mode='member_join')

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not member.guild or member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, 'member_remove')
        if not log_channel:
            return
        await self.send_log(log_channel, member, False, mode='member_remove')

    @Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, 'vc_state_change')
        if not log_channel:
            return
        if before.channel != after.channel:
            if before.channel:
                await self.send_log(log_channel, member, False, mode='member_leave_vc', extra=before.channel)
            if after.channel:
                await self.send_log(log_channel, member, False, mode='member_join_vc', extra=after.channel)
        if before.deaf != after.deaf:
            await self.send_log(log_channel, member, False, mode='member_deaf_vc', extra=after.deaf)
        if before.mute != after.mute:
            await self.send_log(log_channel, member, False, mode='member_mute_vc', extra=after.mute)

    @Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
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
                except discord.Forbidden:
                    pass

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(channel.guild.id, 'channel_delete')
        if log_channel:
            await self.send_log(log_channel, channel, False, mode='channel_role_delete', extra='Channel')

    @Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(role.guild.id, 'role_create')
        if log_channel:
            await self.send_log(log_channel, role, False, mode='channel_role_create', extra='Role')

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(role.guild.id, 'role_delete')
        if log_channel:
            await self.send_log(log_channel, role, False, mode='channel_role_delete', extra='Role')


def setup(bot: rainbot) -> None:
    bot.add_cog(Logging(bot))

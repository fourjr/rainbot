from datetime import datetime, timedelta, timezone  # Add timezone import
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
                    messages = [msg async for msg in i.history(limit=30, after=after)]
                except discord.Forbidden:
                    pass
                else:
                    if not messages:
                        messages = [
                            msg async for msg in i.history(limit=5)
                        ]  # get 5 messages if no messages are recent
                    self.bot._connection._messages += messages

    async def check_enabled(self, guild_id: int, item: Any, channel_id: int = None):
        guild_config = await self.bot.db.get_guild_config(guild_id)

        if channel_id and str(channel_id) in guild_config.ignored_channels[item]:
            return False

        try:
            return self.bot.get_channel(int(guild_config.logs.get(item, 0)))
        except (ValueError, TypeError):
            return guild_config.get(item, False)

    async def send_log(
        self,
        log: discord.TextChannel,
        payload: Union[
            discord.Message,
            discord.User,
            discord.TextChannel,
            discord.VoiceChannel,
            discord.Role,
            discord.Member,
            int,
            discord.RawMessageDeleteEvent,
        ],
        raw: bool,
        end: str = None,
        *,
        mode: str = None,
        extra: Union[discord.Message, bool, discord.VoiceChannel, str] = None,
    ) -> None:
        current_time = datetime.utcnow()
        try:
            guild_id = payload.guild.id
        except AttributeError:
            try:
                guild_id = payload.guild_id
            except AttributeError:
                guild_id = payload.data.get("guild_id")

        guild_config = await self.bot.db.get_guild_config(guild_id)
        current_time += timedelta(hours=guild_config.time_offset)
        # Use Discord local time tag in messages
        current_time = f"<t:{int(current_time.timestamp())}:T>"

        if raw:
            if mode == "bulk":
                await log.send(f"{current_time} Message ({payload.id}) has been {end}.")
            else:
                await log.send(f"{current_time} Message ({payload.message_id}) has been {end}.")
        else:
            if mode == "message_delete":
                try:
                    await log.send(
                        f"{current_time} {payload.author} ({payload.author.id}): Message ({payload.id}) has been deleted in **#{payload.channel.name}** ({payload.channel.id})\n```\n{payload.content}\n```"
                    )
                    # Log attachments if present
                    if getattr(payload, "attachments", None):
                        # Cap to avoid spam
                        max_attachments = 4
                        for index, attachment in enumerate(
                            payload.attachments[:max_attachments], start=1
                        ):
                            ct = (attachment.content_type or "").lower()
                            is_image = ct.startswith(
                                "image/"
                            ) or attachment.filename.lower().endswith(
                                (".png", ".jpg", ".jpeg", ".gif", ".webp")
                            )
                            if is_image:
                                emb = discord.Embed(
                                    title=f"Attachment {index}: {attachment.filename}",
                                    description=f"{attachment.size} bytes\n{attachment.url}",
                                )
                                emb.set_image(url=attachment.url)
                                await log.send(embed=emb)
                            else:
                                await log.send(
                                    f"{current_time} Attachment {index}: {attachment.filename} — {attachment.url}"
                                )
                except discord.HTTPException:
                    # TODO: to implement a more elegant solution
                    await log.send(
                        f"{current_time} {payload.author} ({payload.author.id}): Message ({payload.id}) has been deleted in **#{payload.channel.name}** ({payload.channel.id})"
                    )
                    await log.send(f"```{payload.content}\n```")
            elif mode == "member_join":
                fmt = f"{current_time} {payload} ({payload.id}) has joined. "
                delta = (
                    datetime.now(timezone.utc) - payload.created_at
                )  # Make utcnow timezone-aware
                if delta.total_seconds() < 60 * 60 * 24:
                    # joined in last day
                    fmt += f"Warning: account created {format_timedelta(delta)} ago"
                await log.send(fmt)
            elif mode == "member_remove":
                await log.send(f"{current_time} {payload} ({payload.id}) has left the server.")
            elif mode == "message_edit":
                try:
                    before_text = payload.content or "(no text content)"
                    after_text = extra.content or "(no text content)"
                    await log.send(
                        f"{current_time} {payload.author} ({payload.author.id}): Message ({payload.id}) has been edited in **#{payload.channel.name}** ({payload.channel.id})\n"
                        f"B:```\n{before_text}\n```\nA:\n```\n{after_text}\n```"
                    )
                    # Log attachment differences if present
                    before_atts = getattr(payload, "attachments", []) or []
                    after_atts = getattr(extra, "attachments", []) or []
                    if before_atts or after_atts:
                        before_links = [att.url for att in before_atts]
                        after_links = [att.url for att in after_atts]
                        if before_links:
                            await log.send(
                                f"{current_time} Before attachments ({len(before_links)}):\n"
                                + "\n".join(before_links[:8])
                            )
                        if after_links:
                            await log.send(
                                f"{current_time} After attachments ({len(after_links)}):\n"
                                + "\n".join(after_links[:8])
                            )
                        # Show preview of first after image if available
                        if after_atts:
                            att0 = after_atts[0]
                            ct0 = (att0.content_type or "").lower()
                            if ct0.startswith("image/") or att0.filename.lower().endswith(
                                (".png", ".jpg", ".jpeg", ".gif", ".webp")
                            ):
                                emb = discord.Embed(title="After attachment preview")
                                emb.set_image(url=att0.url)
                                await log.send(embed=emb)
                    # Log embed summary if changed
                    if payload.embeds or extra.embeds:
                        be = payload.embeds[0].to_dict() if payload.embeds else {}
                        ae = extra.embeds[0].to_dict() if extra.embeds else {}
                        if be != ae:
                            be_title = be.get("title")
                            be_desc = be.get("description")
                            ae_title = ae.get("title")
                            ae_desc = ae.get("description")

                            def trunc(s: Any) -> Any:
                                return (s[:60] + "…") if isinstance(s, str) and len(s) > 60 else s

                            await log.send(
                                f"{current_time} Embed updated: "
                                f"title {be_title!r} → {ae_title!r}; "
                                f"desc {trunc(be_desc)!r} → {trunc(ae_desc)!r}"
                            )
                except discord.HTTPException:
                    # to implement a more elegant solution
                    await log.send(
                        f"{current_time} {payload.author} ({payload.author.id}): Message ({payload.id}) has been edited in **#{payload.channel.name}** ({payload.channel.id})"
                    )
                    await log.send(f"B:```\n{payload.content or '(no text content)'}\n```\n")
                    await log.send(f"A:```\n{extra.content or '(no text content)'}\n```")
            elif mode == "member_leave_vc":
                await log.send(
                    f"{current_time} {payload} ({payload.id}) has left :microphone: **{extra}** ({extra.id})."
                )
            elif mode == "member_join_vc":
                await log.send(
                    f"{current_time} {payload} ({payload.id}) has joined :microphone: **{extra}** ({extra.id})."
                )
            elif mode == "member_deaf_vc":
                await log.send(
                    f"{current_time} {payload} ({payload.id}) is{'' if extra else ' not'} deafened"
                )
            elif mode == "member_mute_vc":
                await log.send(
                    f"{current_time} {payload} ({payload.id}) is{'' if extra else ' not'} muted"
                )
            elif mode == "channel_role_create":
                await log.send(f"{current_time} {extra} **{payload}** ({payload.id}) is created")
            elif mode == "channel_role_delete":
                await log.send(f"{current_time} {extra} **{payload}** ({payload.id}) is deleted")
            else:
                raise NotImplementedError(f"{mode} not implemented")

    @Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(
            message.guild.id, "message_delete", message.channel.id
        )
        if not log_channel:
            return
        await self.send_log(log_channel, message, False, mode="message_delete")

    @Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if not payload.cached_message:
            log_channel = await self.check_enabled(
                payload.guild_id, "message_delete", payload.channel_id
            )
            if not payload.guild_id or not log_channel or self.bot.dev_mode:
                return
            await self.send_log(log_channel, payload, True, "deleted")

    @Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.author.bot or self.bot.dev_mode:
            return
        # Proceed only if something material changed (content, embeds, attachments)
        content_changed = (before.content or "") != (after.content or "")
        embeds_changed = (len(before.embeds) != len(after.embeds)) or any(
            (getattr(b.to_dict(), "items", lambda: b.to_dict())() if hasattr(b, "to_dict") else {})
            != (
                getattr(a.to_dict(), "items", lambda: a.to_dict())()
                if hasattr(a, "to_dict")
                else {}
            )
            for b, a in zip(before.embeds, after.embeds)
        )
        before_att = [att.url for att in getattr(before, "attachments", []) or []]
        after_att = [att.url for att in getattr(after, "attachments", []) or []]
        attachments_changed = before_att != after_att
        if not (content_changed or embeds_changed or attachments_changed):
            return
        log_channel = await self.check_enabled(before.guild.id, "message_edit", before.channel.id)
        if not log_channel:
            return
        await self.send_log(log_channel, before, False, mode="message_edit", extra=after)

    @Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if not payload.cached_message:
            log_channel = await self.check_enabled(
                payload.data.get("guild_id"), "message_edit", payload.channel_id
            )
            if not payload.data.get("guild_id") or not log_channel or self.bot.dev_mode:
                return

            # Build a summary for raw edits including content and embed diffs
            new_content = payload.data.get("content")
            embeds = payload.data.get("embeds") or []
            summary_lines = []
            if new_content is not None:
                display = new_content if new_content else "(no text content)"
                summary_lines.append(f"updated text: ```\n{display}\n```")
            if embeds:
                # summarize first embed
                e0 = embeds[0]
                title = e0.get("title")
                desc = e0.get("description")
                summary_lines.append(
                    f"updated embed: title={title!r} desc={(desc[:100] + '…') if (desc and len(desc) > 100) else desc!r}"
                )
            if summary_lines:
                await self.send_log(log_channel, payload, True, " ".join(summary_lines))

    @Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        log_channel = await self.check_enabled(
            payload.guild_id, "message_delete", payload.channel_id
        )
        if not payload.guild_id or not log_channel or self.bot.dev_mode:
            return

        found = [i.id for i in payload.cached_messages]
        for id_ in payload.message_ids:
            if id_ not in found:
                await self.send_log(
                    log_channel, QuickId(payload.guild_id, id_), True, "deleted", mode="bulk"
                )

    @Cog.listener()
    async def on_bulk_message_delete(self, payload: List[discord.Message]) -> None:
        guild_id = payload[0].guild.id
        log_channel = await self.check_enabled(guild_id, "message_delete", payload[0].channel.id)
        if not guild_id or not log_channel or self.bot.dev_mode:
            return

        for message in payload:
            await self.send_log(log_channel, message, False, mode="message_delete")

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not member.guild or member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, "member_join")
        if not log_channel:
            return
        await self.send_log(log_channel, member, False, mode="member_join")

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not member.guild or member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, "member_remove")
        if not log_channel:
            return
        await self.send_log(log_channel, member, False, mode="member_remove")

    @Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.bot or self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(member.guild.id, "vc_state_change")
        if not log_channel:
            return
        if before.channel != after.channel:
            if before.channel:
                await self.send_log(
                    log_channel, member, False, mode="member_leave_vc", extra=before.channel
                )
            if after.channel:
                await self.send_log(
                    log_channel, member, False, mode="member_join_vc", extra=after.channel
                )
        if before.deaf != after.deaf:
            await self.send_log(log_channel, member, False, mode="member_deaf_vc", extra=after.deaf)
        if before.mute != after.mute:
            await self.send_log(log_channel, member, False, mode="member_mute_vc", extra=after.mute)

    @Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(channel.guild.id, "channel_create")
        if log_channel:
            await self.send_log(
                log_channel, channel, False, mode="channel_role_create", extra="Channel"
            )

        # Setup mute role perms
        guild_config = await self.bot.db.get_guild_config(channel.guild.id)
        if guild_config.mute_role:
            role = discord.utils.get(channel.guild.roles, id=int(guild_config["mute_role"]))
            if isinstance(
                channel, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel)
            ):
                try:
                    await channel.set_permissions(role, send_messages=False, speak=False)
                except discord.Forbidden:
                    pass

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(channel.guild.id, "channel_delete", channel.id)
        if log_channel:
            await self.send_log(
                log_channel, channel, False, mode="channel_role_delete", extra="Channel"
            )

    @Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(role.guild.id, "role_create")
        if log_channel:
            await self.send_log(log_channel, role, False, mode="channel_role_create", extra="Role")

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if self.bot.dev_mode:
            return
        log_channel = await self.check_enabled(role.guild.id, "role_delete")
        if log_channel:
            await self.send_log(log_channel, role, False, mode="channel_role_delete", extra="Role")


async def setup(bot: rainbot) -> None:
    await bot.add_cog(Logging(bot))

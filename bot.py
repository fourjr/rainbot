import asyncio
import logging
import os
import sys
import traceback
from datetime import datetime, timedelta
from time import time
from typing import Any, Dict, List, Optional, Union

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

from ext import errors
from ext.database import DatabaseManager
from ext.errors import Underleveled
from ext.utility import format_timedelta, tryint


class rainbot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(command_prefix=None, max_messages=10000, intents=intents, allowed_mentions=discord.AllowedMentions.none())

        self.accept = '<:check:684169254618398735>'
        self.deny = '<:xmark:684169254551158881>'
        self.dev_mode = os.name == 'nt'
        self.session: Optional[aiohttp.ClientSession] = None

        # Set up logging
        self.logger = logging.getLogger('rainbot')
        if self.dev_mode:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        self.logger.addHandler(handler)

        self.db = DatabaseManager(os.environ['mongo'], loop=self.loop)

        self.owners = list(map(int, os.getenv('owners', '').split(',')))

        self.remove_command('help')
        self.load_extensions()

        if not self.dev_mode:
            self.loop.run_until_complete(self.setup_unmutes())
        try:
            self.loop.run_until_complete(self.start(os.getenv('token')))
        except discord.LoginFailure:
            self.logger.error('Invalid token')
        except KeyboardInterrupt:
            self.loop.run_until_complete(self.logout())
        except Exception:
            self.logger.error('Fatal exception')
            traceback.print_exc(file=sys.stderr)
        finally:
            if self.session:
                self.loop.run_until_complete(self.session.close())
            self.loop.close()
            os._exit(0)

    def load_extensions(self) -> None:
        for i in os.listdir('cogs'):
            if i.endswith('.py'):
                if self.dev_mode and i in ('logs.py'):
                    continue
                try:
                    self.load_extension(f'cogs.{i.replace(".py", "")}')
                except:
                    self.logger.exception(f'Failed to load cogs/{i}')
                else:
                    self.logger.info(f'Loaded {i}')
        self.logger.info('All extensions loaded.')

    async def on_message(self, message: discord.Message) -> None:
        if not message.author.bot and message.guild:
            ctx = await self.get_context(message)
            await self.invoke(ctx)

    async def get_prefix(self, message: discord.Message) -> Union[str, List[str]]:
        if self.dev_mode:
            return './'
        guild_config = await self.db.get_guild_config(message.guild.id)
        return commands.when_mentioned_or(guild_config.prefix)(self, message)

    async def on_connect(self) -> None:
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.logger.info('Connected')

    async def on_ready(self) -> None:
        self.logger.info('Ready')
        self.logger.debug('Debug mode ON: Prefix ./')

    async def on_command_error(self, ctx: commands.Context, e: Exception) -> None:
        e = getattr(e, 'original', e)
        ignored = (
            commands.CommandNotFound,
            commands.CheckFailure,
            commands.BadArgument,
            Underleveled
        )
        if isinstance(e, (commands.UserInputError, errors.BotMissingPermissionsInChannel)):
            await ctx.invoke(self.get_command('help'), command_or_cog=ctx.command.qualified_name, error=e)
        elif isinstance(e, discord.Forbidden):
            await ctx.invoke(self.get_command('help'), command_or_cog=ctx.command.qualified_name, error=Exception('Bot has insufficient permissions'))
        elif isinstance(e, ignored) and not self.dev_mode:
            pass
        else:
            self.logger.exception(f'Error while executing {ctx.command} ({ctx.message.content}) in Guild {ctx.guild.id} by User {ctx.author.id}', exc_info=(type(e), e, e.__traceback__))

    async def setup_unmutes(self) -> None:
        data = self.db.coll.find({'mutes': {'$exists': True, '$ne': []}})
        async for d in data:
            for m in d['mutes']:
                self.loop.create_task(self.unmute(int(d['guild_id']), int(m['member']), m['time']))

    async def setup_unbans(self) -> None:
        data = self.db.coll.find({'tempbans': {'$exists': True, '$ne': []}})
        async for d in data:
            for m in d['tempbans']:
                self.loop.create_task(self.unban(int(d['guild_id']), int(m['member']), m['time']))

    async def on_member_join(self, m: discord.Member) -> None:
        """Set up mutes if the member rejoined to bypass a mute"""
        if not self.dev_mode:
            guild_config = await self.db.get_guild_config(m.guild.id)
            mutes = guild_config.mutes
            user_mute = None

            for mute in mutes:
                if mute['member'] == str(m.id):
                    user_mute = mute

            if user_mute:
                await self.mute(m.guild.me, m, user_mute['time'] - time(), 'Mute evasion', modify_db=False)

    async def mute(self, actor: discord.Member, member: discord.Member, delta: timedelta, reason: str, modify_db: bool=True) -> None:
        """Mutes a ``member`` for ``delta``"""
        guild_config = await self.db.get_guild_config(member.guild.id)
        mute_role = discord.utils.get(member.guild.roles, id=int(guild_config.mute_role or 0))
        if not mute_role:
            # mute role
            mute_role = discord.utils.get(member.guild.roles, name='Muted')
            if not mute_role:
                # existing mute role not found, let's create one
                mute_role = await member.guild.create_role(
                    name='Muted', color=discord.Color(0x818689), reason='Attempted to mute user but role did not exist'
                )
                for tc in member.guild.text_channels:
                    try:
                        await tc.set_permissions(mute_role, send_messages=False, reason='Attempted to mute user but role did not exist')
                    except discord.Forbidden:
                        pass
                for vc in member.guild.voice_channels:
                    try:
                        await vc.set_permissions(mute_role, speak=False, reason='Attempted to mute user but role did not exist')
                    except discord.Forbidden:
                        pass

            await self.db.update_guild_config(member.guild.id, {'$set': {'mute_role': str(mute_role.id)}})
        await member.add_roles(mute_role)

        # mute complete, log it
        log_channel: discord.TextChannel = self.get_channel(tryint(guild_config.modlog.member_mute))
        if log_channel:
            current_time = datetime.utcnow()

            offset = guild_config.time_offset
            current_time += timedelta(hours=offset)
            current_time_fmt = current_time.strftime('%H:%M:%S')

            await log_channel.send(f"`{current_time_fmt}` {actor} has muted {member} ({member.id}), reason: {reason} for {format_timedelta(delta)}")

        if delta:
            duration = delta.total_seconds()
            # log complete, save to DB
            if duration is not None:
                duration += time()
                if modify_db:
                    await self.db.update_guild_config(member.guild.id, {'$push': {'mutes': {'member': str(member.id), 'time': duration}}})
                self.loop.create_task(self.unmute(member.guild.id, member.id, duration))

    async def unmute(self, guild_id: int, member_id: int, duration: Optional[float], reason: str='Auto') -> None:
        await self.wait_until_ready()
        if duration is not None:
            await asyncio.sleep(duration - time())

        try:
            member = self.get_guild(guild_id).get_member(member_id)
            member.guild.id
        except AttributeError:
            member = None

        if member:
            guild_config = await self.db.get_guild_config(guild_id)
            mute_role: Optional[discord.Role] = discord.utils.get(member.guild.roles, id=int(guild_config.mute_role))
            log_channel: Optional[discord.TextChannel] = self.get_channel(tryint(guild_config.modlog.member_unmute))

            current_time = datetime.utcnow()

            offset = guild_config.time_offset
            current_time += timedelta(hours=offset)
            current_time_fmt = current_time.strftime('%H:%M:%S')

            if member:
                if mute_role in member.roles:
                    await member.remove_roles(mute_role)
                    if log_channel:
                        await log_channel.send(f"`{current_time_fmt}` {member} ({member.id}) has been unmuted. Reason: {reason}")
            else:
                if log_channel:
                    await log_channel.send(f"`{current_time_fmt}` Tried to unmute {member} ({member.id}), member not in server")

        # set db
        pull: Dict[str, Any] = {'$pull': {'mutes': {'member': str(member_id)}}}
        if duration is not None:
            pull['$pull']['mutes']['time'] = duration
        await self.db.update_guild_config(guild_id, pull)

    async def unban(self, guild_id: int, member_id: int, duration: Optional[float], reason: str='Auto') -> None:
        await self.wait_until_ready()
        if duration is not None:
            await asyncio.sleep(duration - time())

        guild = self.get_guild(guild_id)

        if guild:
            guild_config = await self.db.get_guild_config(guild_id)
            log_channel: Optional[discord.TextChannel] = self.get_channel(tryint(guild_config.modlog.member_unban))

            current_time = datetime.utcnow()

            offset = guild_config.time_offset
            current_time += timedelta(hours=offset)
            current_time_fmt = current_time.strftime('%H:%M:%S')

            try:
                await guild.unban(discord.Object(member_id), reason=reason)
            except discord.NotFound:
                pass
            else:
                if log_channel:
                    user = self.get_user(member_id)
                    name = getattr(user, 'name', '(no name)')
                    await log_channel.send(f"`{current_time_fmt}` {name} ({member_id}) has been unbanned. Reason: {reason}")

        # set db
        pull: Dict[str, Any] = {'$pull': {'tempbans': {'member': str(member_id)}}}
        if duration is not None:
            pull['$pull']['tempbans']['time'] = duration
        await self.db.update_guild_config(guild_id, pull)


if __name__ == '__main__':
    load_dotenv()
    rainbot()

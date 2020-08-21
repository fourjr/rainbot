import asyncio
import discord
import logging
import sys
import traceback
import os
from datetime import datetime, timedelta
from time import time

import aiohttp
from discord.ext import commands
from dotenv import load_dotenv

from ext import errors
from ext.database import DatabaseManager
from ext.state import ConnState
from ext.utils import format_timedelta


class rainbot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=None)

        self.accept = '<:check:684169254618398735>'
        self.deny = '<:xmark:684169254551158881>'
        self.dev_mode = os.name == 'nt'

        # Set up logging
        self.logger = logging.getLogger('rainbot')
        if self.dev_mode:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        self.logger.addHandler(handler)

        self.db = DatabaseManager(os.getenv('mongo'), loop=self.loop)

        self.owners = list(map(int, os.getenv('owners', '').split(',')))

        self.remove_command('help')
        self.load_extensions()

        self._connection = ConnState(dispatch=self.dispatch, handlers=self._handlers,
                                     hooks=self._hooks, syncer=self._syncer, http=self.http, loop=self.loop, max_messages=10000)
        self._connection.shard_count = self.shard_count
        self._connection._get_websocket = self._get_websocket

        # self.loop.run_until_complete(self.cache_mutes())
        if not self.dev_mode:
            self.loop.run_until_complete(self.setup_unmutes())
        try:
            self.run(os.getenv('token'))
        except discord.LoginFailure:
            self.logger.error('Invalid token')
        except KeyboardInterrupt:
            pass
        except Exception:
            self.logger.error('Fatal exception')
            traceback.print_exc(file=sys.stderr)

    def load_extensions(self):
        for i in os.listdir('cogs'):
            if i.endswith('.py'):
                try:
                    self.load_extension(f'cogs.{i.replace(".py", "")}')
                except:
                    self.logger.exception(f'Failed to load cogs/{i}')
                else:
                    self.logger.info(f'Loaded {i}')
        self.logger.info('All extensions loaded.')

    async def on_message(self, message):
        if not message.author.bot and message.guild:
            ctx = await self.get_context(message)
            await self.invoke(ctx)

    async def get_prefix(self, message):
        if self.dev_mode:
            return './'
        guild_config = await self.db.get_guild_config(message.guild.id)
        return commands.when_mentioned_or(guild_config.prefix)(self, message)

    async def on_connect(self):
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.logger.info('Connected')

    async def on_ready(self):
        self.logger.info('Ready')
        self.logger.debug('Debug mode ON: Prefix ./')

    async def on_command_error(self, ctx, e):
        e = getattr(e, 'original', e)
        ignored = (
            commands.CommandNotFound,
            commands.CheckFailure,
            commands.BadArgument
        )
        if isinstance(e, (commands.UserInputError, errors.BotMissingPermissionsInChannel)):
            await ctx.invoke(self.get_command('help'), command_or_cog=ctx.command.qualified_name, error=e)
        elif isinstance(e, (discord.Forbidden)):
            await ctx.invoke(self.get_command('help'), command_or_cog=ctx.command.qualified_name, error=Exception('Bot has insufficient permissions'))
        elif isinstance(e, ignored) and not self.dev_mode:
            pass
        else:
            self.logger.exception(f'Error while executing {ctx.command} ({ctx.message.content})', exc_info=(type(e), e, e.__traceback__))

    async def setup_unmutes(self):
        data = self.db.coll.find({'mutes': {'$exists': True, '$ne': []}})
        async for d in data:
            for m in d['mutes']:
                self.loop.create_task(self.unmute(d['guild_id'], m['member'], m['time']))

    async def cache_mutes(self):
        self.mutes = await self.db.coll.find({'mutes': {'$exists': True, '$ne': []}})

    async def on_member_join(self, m):
        """Set up mutes if the member rejoined to bypass a mute"""
        if not self.dev_mode:
            guild_config = await self.db.get_guild_config(m.guild.id)
            mutes = guild_config.mutes
            user_mute = None

            for mute in mutes:
                if mute['member'] == str(m.id):
                    user_mute = mute

            if user_mute:
                self.mute(m, user_mute['time'] - time(), 'Mute evasion', modify_db=False)

    async def mute(self, member, delta, reason, modify_db=True):
        """Mutes a ``member`` for ``delta`` seconds"""
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
                for c in member.guild.text_channels:
                    try:
                        await c.set_permissions(mute_role, send_messages=False, reason='Attempted to mute user but role did not exist')
                    except discord.Forbidden:
                        pass
                for c in member.guild.voice_channels:
                    try:
                        await c.set_permissions(mute_role, speak=False, reason='Attempted to mute user but role did not exist')
                    except discord.Forbidden:
                        pass

            await self.db.update_guild_config(member.guild.id, {'$set': {'mute_role': str(mute_role.id)}})
        await member.add_roles(mute_role)

        # mute complete, log it
        log_channel = self.get_channel(int(guild_config.modlog.member_mute or 0))
        if log_channel:
            current_time = datetime.utcnow()

            offset = guild_config.time_offset
            current_time += timedelta(hours=offset)
            current_time = current_time.strftime('%H:%M:%S')

            await log_channel.send(f"`{current_time}` Member {member} ({member.id}) has been muted for reason: {reason} for {format_timedelta(delta)}")

        if delta:
            duration = delta.total_seconds()
            # log complete, save to DB
            if duration is not None:
                duration += time()
                if modify_db:
                    await self.db.update_guild_config(member.guild.id, {'$push': {'mutes': {'member': str(member.id), 'time': duration}}})
                self.loop.create_task(self.unmute(member.guild.id, member.id, duration))

    async def unmute(self, guild_id, member_id, duration, reason='Auto'):
        await self.wait_until_ready()
        if duration is not None:
            await asyncio.sleep(duration - time())

        try:
            member = self.get_guild(int(guild_id)).get_member(int(member_id))
            member.guild.id
        except AttributeError:
            member = None

        if member:
            guild_config = await self.db.get_guild_config(guild_id)
            mute_role = discord.utils.get(member.guild.roles, id=int(guild_config.mute_role))
            log_channel = None

            if guild_config.modlog.member_unmute:
                log_channel = self.get_channel(int(guild_config.modlog.member_unmute))

            current_time = datetime.utcnow()

            offset = guild_config.time_offset
            current_time += timedelta(hours=offset)
            current_time = current_time.strftime('%H:%M:%S')

            if member:
                if mute_role in member.roles:
                    await member.remove_roles(mute_role)
                    if log_channel:
                        await log_channel.send(f"`{current_time}` {member} ({member.id}) has been unmuted. Reason: {reason}")
            else:
                if log_channel:
                    await log_channel.send(f"`{current_time}` Tried to unmute {member} ({member.id}), member not in server")

        # set db
        pull = {'$pull': {'mutes': {'member': str(member_id)}}}
        if duration is not None:
            pull['$pull']['mutes']['time'] = duration
        await self.db.update_guild_config(guild_id, pull)


if __name__ == '__main__':
    load_dotenv()
    rainbot()

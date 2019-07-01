import asyncio
import discord
import logging
import requests
import sys
import traceback
import os
from datetime import datetime, timedelta
from time import time

import aiohttp
from discord.ext import commands
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from ext import errors
from ext.state import ConnState
from ext.context import RainContext


class rainbot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=None)

        self.session = aiohttp.ClientSession(loop=self.loop)
        self.accept = 'Operation completed successfully!'
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

        self.mongo = AsyncIOMotorClient(os.getenv('mongo'))
        self.logger.info('Connected to Mongo')

        self.remove_command('help')
        self.load_extensions()

        self._connection = ConnState(dispatch=self.dispatch, chunker=self._chunker, handlers=self._handlers,
                                     syncer=self._syncer, http=self.http, loop=self.loop, max_messages=100000)

        # self.loop.run_until_complete(self.setup_unmutes())
        try:
            self.run(os.getenv('token'))
        except discord.LoginFailure:
            print('Invalid token')
        except KeyboardInterrupt:
            pass
        except Exception:
            print('Fatal exception')
            traceback.print_exc(file=sys.stderr)
        finally:
            requests.get(f'https://fourjr-herokustartup.herokuapp.com/logout/{os.getenv("HEROKU_APP_NAME")}')

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
            ctx = await self.get_context(message, cls=RainContext)
            await self.invoke(ctx)

    async def get_prefix(self, message):
        if self.dev_mode:
            return './'
        guild_info = await self.mongo.config.guilds.find_one({'guild_id': str(message.guild.id)}) or {}
        return commands.when_mentioned_or(guild_info.get('prefix', '!!'))(self, message)

    async def on_connect(self):
        self.logger.info('Connected')

    async def on_ready(self):
        self.logger.info('Ready')

    async def on_command_error(self, ctx, e):
        e = getattr(e, 'original', e)
        ignored = (
            commands.CommandNotFound,
            commands.CheckFailure,
            discord.Forbidden
        )
        if isinstance(e, (commands.UserInputError, errors.BotMissingPermissionsInChannel)):
            await ctx.invoke(self.get_command('help'), command_or_cog=ctx.command.qualified_name, error=e)
        elif isinstance(e, ignored):
            pass
        else:
            self.logger.exception(f'Error while executing {ctx.command} ({ctx.message.content})', exc_info=(type(e), e, e.__traceback__))

    async def setup_unmutes(self):
        data = self.mongo.config.guilds.find({'mutes': {'$exists': True, '$ne': []}})
        async for d in data:
            for m in d['mutes']:
                self.loop.create_task(self.unmute(d['guild_id'], m['member'], m['time']))

    async def mute(self, member, duration, reason):
        """Mutes a ``member`` for ``duration`` seconds"""
        guild_info = await self.mongo.config.guilds.find_one({'guild_id': str(member.guild.id)}) or {}
        mute_role = discord.utils.get(member.guild.roles, id=int(guild_info.get('mute_role') or 0))
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

            await self.mongo.config.guilds.find_one_and_update({'guild_id': str(member.guild.id)}, {'$set': {'mute_role': str(mute_role.id)}}, upsert=True)
        await member.add_roles(mute_role)

        # mute complete, log it
        log_channel = self.get_channel(int(guild_info.get('modlog', {}).get('member_mute') or 0))
        if log_channel:
            current_time = datetime.utcnow()

            offset = guild_info.get('time_offset', 0)
            current_time += timedelta(hours=offset)
            current_time = current_time.strftime('%H:%M:%S')

            await log_channel.send(f"`{current_time}` Member {member} ({member.id}) has been muted for reason: {reason} for {duration} seconds")

        # log complete, save to DB
        if duration is not None:
            duration += time()
            await self.mongo.config.guilds.find_one_and_update({'guild_id': str(member.guild.id)}, {'$push': {'mutes': {'member': str(member.id), 'time': duration}}}, upsert=True)
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

        print(guild_id, member_id, duration, reason, member)
        if member:
            print('ran')
            guild_info = await self.mongo.config.guilds.find_one({'guild_id': str(member.guild.id)}) or {}
            mute_role = discord.utils.get(member.guild.roles, id=int(guild_info.get('mute_role', 0)))

            log_channel = self.get_channel(int(guild_info.get('modlog', {}).get('member_unmute') or 0))
            current_time = datetime.utcnow()

            offset = guild_info.get('time_offset', 0)
            current_time += timedelta(hours=offset)
            current_time = current_time.strftime('%H:%M:%S')

            if member:
                if mute_role in member.roles:
                    await member.remove_roles(mute_role)
                    if log_channel:
                        await log_channel.send(f"`{current_time}` {member} ({member.id}) has been unmuted. Reason: {reason}")
            else:
                await log_channel.send(f"`{current_time}` Tried to unmute {member} ({member.id}), member not in server")

        # set db
        pull = {'$pull': {'mutes': {'member': str(member_id)}}}
        if duration is not None:
            pull['$pull']['mutes']['time'] = duration
        await self.mongo.config.guilds.find_one_and_update({'guild_id': str(guild_id)}, pull)


if __name__ == '__main__':
    load_dotenv()
    requests.get(f'https://fourjr-herokustartup.herokuapp.com/login/{os.getenv("HEROKU_APP_NAME")}')
    rainbot()

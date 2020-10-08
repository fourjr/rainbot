import inspect
import io
import subprocess
import textwrap
import traceback
import os
from contextlib import redirect_stdout
from datetime import datetime

import discord
from discord.ext import commands

from ext.command import RainCommand, RainGroup, command
from ext.paginator import Paginator
from ext.utils import get_perm_level, get_command_level, owner


class Utility(commands.Cog):
    """General utility commands"""

    def __init__(self, bot):
        self.bot = bot
        self.order = 4

    @owner()
    @command(0, name='eval')
    async def _eval(self, ctx, *, body):
        """Evaluates python code"""
        env = {
            'ctx': ctx,
            'self': self,
            'bot': self.bot,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            'source': inspect.getsource,
        }

        env.update(globals())

        def cleanup_code(content):
            """Automatically removes code blocks from the code."""
            # remove ```py\n```
            if content.startswith('```') and content.endswith('```'):
                return '\n'.join(content.split('\n')[1:-1])

            # remove `foo`
            return content.strip('` \n')

        body = cleanup_code(body)
        stdout = io.StringIO()
        err = out = None

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        def paginate(text: str):
            '''Simple generator that paginates text.'''
            last = 0
            pages = []
            for curr in range(0, len(text)):
                if curr % 1980 == 0:
                    pages.append(text[last:curr])
                    last = curr
                    appd_index = curr
            if appd_index != len(text) - 1:
                pages.append(text[last:curr])
            return list(filter(lambda a: a != '', pages))

        try:
            exec(to_compile, env)
        except Exception as e:
            err = await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
            return await ctx.message.add_reaction('\u2049')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            err = await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        out = await ctx.send(f'```py\n{value}\n```')
                    except:
                        paginated_text = paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                out = await ctx.send(f'```py\n{page}\n```')
                                break
                            await ctx.send(f'```py\n{page}\n```')
            else:
                try:
                    out = await ctx.send(f'```py\n{value}{ret}\n```')
                except:
                    paginated_text = paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            out = await ctx.send(f'```py\n{page}\n```')
                            break
                        await ctx.send(f'```py\n{page}\n```')

        if out:
            await ctx.message.add_reaction('\u2705')  # tick
        elif err:
            await ctx.message.add_reaction('\u2049')  # x
        else:
            await ctx.message.add_reaction('\u2705')

    @owner()
    @command(0, name='exec')
    async def _exec(self, ctx, *, command):
        """Executes code in the command line"""
        cmd = subprocess.run(command, cwd=os.getcwd(), stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
        err = cmd.stderr.decode('utf-8')
        res = cmd.stdout.decode('utf-8')
        if len(res) > 1850 or len(err) > 1850:
            async with self.bot.session.post('https://hasteb.in/documents', data=err or res) as resp:
                data = await resp.json()
            await ctx.send(f"Output: <https://hasteb.in/{data['key']}.txt>")
        else:
            await ctx.send(f'```{err or res}```')

    @owner()
    @command(0)
    async def update(self, ctx):
        """Updates the bot"""
        # command fetches from git, gets a list of updated file in stdout, merges updated into local
        cmd = subprocess.run('git fetch && git diff --name-only ..origin && git merge FETCH_HEAD -q', cwd=os.getcwd(), stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
        res = cmd.stdout.decode('utf-8')

        if res == '':
            await ctx.send('Already up to date.')
        else:
            # Something other than a cog is modified
            for fn in res.splitlines():
                if fn.split('/')[0] != 'cogs':
                    await ctx.send('Bot restarting...')
                    subprocess.Popen('sudo systemctl restart rainbot', cwd=os.getcwd(), shell=True)
                    return

            # Only cogs are modified, so just reload all of the modified cogs
            fmt = ''
            for fn in res.splitlines():
                if fn.split('/')[0] == 'cogs':
                    cog_name = '.'.join(fn.split('/'))
                    self.bot.unload_extension(cog_name[:-3])
                    self.bot.load_extension(cog_name[:-3])
                    fmt += f'Reloaded {cog_name[:-3]}\n'

            await ctx.send(fmt)

    async def can_run(self, ctx, cmd):
        ctx.command = cmd
        can_run = True
        if cmd.checks:
            try:
                can_run = (await discord.utils.async_all(predicate(ctx) for predicate in cmd.checks))
            except commands.CheckFailure:
                can_run = False
        return can_run

    async def format_cog_help(self, ctx, prefix, cog):
        em = discord.Embed(title=cog.__class__.__name__, description=cog.__doc__ or "", color=0x7289da)
        commands = []
        fmt = ''
        # maxlen = 0

        for i in inspect.getmembers(cog, predicate=lambda x: isinstance(x, (RainCommand, RainGroup))):
            if i[1].parent:
                # Ignore subcommands
                continue
            if await self.can_run(ctx, i[1]):
                commands.append(i[1])

        for i in commands:
            proposed_fmt = fmt + f"`{prefix}{i.name}` {i.short_doc}\n"
            if len(proposed_fmt) > 1024:
                em.add_field(name='Commands', value=fmt)
                proposed_fmt = proposed_fmt[len(fmt)]
            fmt = proposed_fmt

        if fmt:
            em.add_field(name='Commands', value=fmt)

        if em.fields:
            return em

    async def format_command_help(self, ctx, prefix, cmd):
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        cmd_level = get_command_level(cmd, guild_config)

        if isinstance(cmd, RainCommand):
            if await self.can_run(ctx, cmd) and cmd.enabled:
                em = discord.Embed(title=prefix + cmd.signature, description=f'{cmd.help}\n\nPermission level: {cmd_level}', color=0x7289da)
                return em

        elif isinstance(cmd, RainGroup):
            em = discord.Embed(title=prefix + cmd.signature, description=f'{cmd.help}\n\nPermission level: {cmd_level}', color=0x7289da)
            subcommands = ''
            commands = []

            for i in cmd.commands:
                if await self.can_run(ctx, i):
                    commands.append(i)

            for i in commands:
                subcommands += f"`{i.name}` {i.short_doc}\n"

            em.add_field(name='Subcommands', value=subcommands)
            return em

    @command(0, name='help')
    async def help_(self, ctx, *, command_or_cog=None, error=None):
        """Shows the help message"""
        if error:
            error = await commands.clean_content(escape_markdown=True).convert(ctx, str(error))
            error = f'{self.bot.deny} `{error}`'
        prefix = (await self.bot.db.get_guild_config(ctx.guild.id)).prefix
        invalid_command = discord.Embed(title='Invalid command or cog name.', color=0xff0000)

        if command_or_cog:
            cmd = self.bot.get_command(command_or_cog.lower())
            if not cmd:
                cog = self.bot.get_cog(command_or_cog.title())
                if not cog:
                    return await ctx.send(content=error, embed=invalid_command)

                em = await self.format_cog_help(ctx, prefix, cog)
                await ctx.send(content=error, embed=em or invalid_command)
            else:
                em = await self.format_command_help(ctx, prefix, cmd)
                await ctx.send(content=error, embed=em or invalid_command)
        else:
            ems = []
            for i in sorted(self.bot.cogs.values(), key=lambda x: getattr(x, 'order', 100)):
                em = await self.format_cog_help(ctx, prefix, i)
                if em:
                    ems.append(em)

            await Paginator(ctx, *ems).start()

    @command(0)
    async def about(self, ctx):
        """About rainbot"""
        await ctx.send('**What is rainbot?**\nrainbot is an full-fledged custom moderation bot!\nLook at <https://github.com/fourjr/rainbot/wiki/About> for more information.\n\nInvite: <https://discord.com/oauth2/authorize?client_id=372748944448552961&scope=bot&permissions=2013785334>\nSupport Server: https://discord.gg/eXrDpGS')

    @command(0)
    async def invite(self, ctx):
        """Invite rainbot to your own server!"""
        await ctx.send('<https://discord.com/oauth2/authorize?client_id=372748944448552961&scope=bot&permissions=2013785334>')

    @command(0)
    async def server(self, ctx):
        """Join the support server for rainbot!"""
        await ctx.send('Join the rainbot support server: https://discord.gg/eXrDpGS')

    @command(0)
    async def mylevel(self, ctx):
        """Checks your permission level"""
        perm_level = get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))
        await ctx.send(f'You are on level {perm_level[0]} ({perm_level[1]})')

    @command(0)
    async def ping(self, ctx):
        """Pong!"""
        ts = datetime.utcnow() - ctx.message.created_at
        await ctx.send(f'Pong!\nWS Latency: {self.bot.latency * 1000:.2f}ms\nMessage Latency: {ts.total_seconds() * 1000:.2f}ms')

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        channel = self.bot.get_channel(733702521893289985)
        if channel:
            await channel.send(f'Joined {guild.name} ({guild.id}) [{len(guild.members)} members] - Total: {len(self.bot.guilds)}')

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        channel = self.bot.get_channel(733702521893289985)
        if channel:
            await channel.send(f'Left {guild.name} ({guild.id}) [{len(guild.members)} members] - Total: {len(self.bot.guilds)}')


def setup(bot):
    bot.add_cog(Utility(bot))

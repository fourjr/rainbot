import inspect
import io
import textwrap
import traceback
from contextlib import redirect_stdout

import discord
from discord.ext import commands

from ext.utils import owner, get_perm_level
from ext.command import command, RainCommand, RainGroup
from ext.paginator import Paginator


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
    @command(0)
    async def sudo(self, ctx, member: discord.Member, *, content):
        """Sends a message on behalf of the user"""
        ctx.message.author = member
        ctx.message.content = content
        await self.bot.process_commands(ctx.message)

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
            if await self.can_run(ctx, i[1]):
                commands.append(i[1])

        # for i in commands:
        #     cmdlen = len(f'`{prefix}{i.name}`')
        #     if cmdlen > maxlen:
        #         maxlen = cmdlen

        for i in commands:
            # cmdlen = len(f'`{prefix}{i.name}`')
            # proposed_fmt = fmt + f"`{prefix}{i.name}` {' ' * (maxlen - cmdlen)}{i.short_doc}\n"
            proposed_fmt = fmt + f"`{prefix}{i.name}` {i.short_doc}\n"
            if len(proposed_fmt) > 1024:
                em.add_field(name=u'\u200b', value=fmt)
                proposed_fmt = proposed_fmt[len(fmt)]
            fmt = proposed_fmt

        if fmt:
            em.add_field(name=u'\u200b', value=fmt)

        if em.fields:
            return em

    async def format_command_help(self, ctx, prefix, cmd):
        if isinstance(cmd, RainCommand):
            if await self.can_run(ctx, cmd) and cmd.enabled:
                em = discord.Embed(title=prefix + cmd.signature, description=f'{cmd.help}\n\nPermission level: {cmd.perm_level}', color=0x7289da)
                return em

        elif isinstance(cmd, RainGroup):
            em = discord.Embed(title=prefix + cmd.signature, description=f'{cmd.help}\n\nPermission level: {cmd.perm_level}', color=0x7289da)
            subcommands = ''
            # maxlen = 0
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
            error = f'<:xmark:684169254551158881> `{error}`'
        prefix = (await ctx.guild_config()).get('prefix', '!!')
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
            for i in self.bot.cogs.values():
                em = await self.format_cog_help(ctx, prefix, i)
                if em:
                    ems.append(em)

            await Paginator(ctx, *ems).start()

    @command(0)
    async def about(self, ctx):
        await ctx.send('**What is rainbot?**\nrainbot is an invite-only moderation bot that any server can get by applying!\nLook at <https://github.com/fourjr/rainbot/wiki/About> for more information')

    @command(0)
    async def mylevel(self, ctx):
        """Checks your permission level"""
        perm_level = get_perm_level(ctx.author, await ctx.guild_config())
        await ctx.send(f'You are on level {perm_level[0]} ({perm_level[1]})')


def setup(bot):
    bot.add_cog(Utility(bot))

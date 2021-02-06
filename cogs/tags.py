import json
from typing import Any, Dict, Union

import discord
from discord.ext import commands

from bot import rainbot
from ext.command import group
from ext.utility import apply_vars


class Tags(commands.Cog):
    def __init__(self, bot: rainbot) -> None:
        self.bot = bot

    @group(6, invoke_without_command=True)
    async def tag(self, ctx: commands.Context) -> None:
        """Controls tags in your server"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='tag')

    @tag.command(6)
    async def create(self, ctx: commands.Context, name: str, *, value: commands.clean_content) -> None:
        """Create tags for your server.

        Example: tag create hello Hi! I am the bot responding!
        Complex usage: https://github.com/fourjr/rainbot/wiki/Tags
        """
        if value.startswith('http'):
            if value.startswith('https://hastebin.cc') and 'raw' not in value:
                value = 'https://hastebin.cc/raw/' + value[18:]

            async with self.bot.session.get(value) as resp:
                value = await resp.text()

        if name in [i.qualified_name for i in self.bot.commands]:
            await ctx.send('Name is already a pre-existing bot command')
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$push': {'tags': {'name': name, 'value': value}}})
            await ctx.send(self.bot.accept)

    @tag.command(6)
    async def remove(self, ctx: commands.Context, name: str) -> None:
        """Removes a tag"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'tags': {'name': name}}})

        await ctx.send(self.bot.accept)

    @tag.command(6, name='list')
    async def list_(self, ctx: commands.Context) -> None:
        """Lists all tags"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        tags = [i.name for i in guild_config.tags]

        if tags:
            await ctx.send('Tags: ' + ', '.join(tags))
        else:
            await ctx.send('No tags saved')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.author.bot and message.guild:
            ctx = await self.bot.get_context(message)
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            tags = [i.name for i in guild_config.tags]

            if ctx.invoked_with in tags:
                tag = guild_config.tags.get_kv('name', ctx.invoked_with)
                user_input = message.content.replace(f'{ctx.prefix}{ctx.invoked_with}', '', 1).strip()
                await ctx.send(**self.format_message(tag.value, message, user_input))

    def apply_vars_dict(self, tag: Dict[str, Union[Any]], message: discord.Message, user_input: str) -> Dict[str, Union[Any]]:
        for k, v in tag.items():
            if isinstance(v, dict):
                tag[k] = self.apply_vars_dict(v, message, user_input)
            elif isinstance(v, str):
                tag[k] = apply_vars(self.bot, v, message, user_input)
            elif isinstance(v, list):
                tag[k] = [self.apply_vars_dict(_v, message, user_input) for _v in v]
            if k == 'timestamp':
                tag[k] = v[:-1]
        return tag

    def format_message(self, tag: str, message: discord.Message, user_input: str) -> Dict[str, Union[Any]]:
        updated_tag: Dict[str, Union[Any]]
        try:
            updated_tag = json.loads(tag)
        except json.JSONDecodeError:
            # message is not embed
            tag = apply_vars(self.bot, tag, message, user_input)
            updated_tag = {'content': tag}
        else:
            # message is embed
            updated_tag = self.apply_vars_dict(updated_tag, message, user_input)

            if 'embed' in updated_tag:
                updated_tag['embed'] = discord.Embed.from_dict(updated_tag['embed'])
            else:
                updated_tag = None
        return updated_tag


def setup(bot: rainbot) -> None:
    bot.add_cog(Tags(bot))

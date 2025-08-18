import json
from typing import Any, Dict, Union

import discord
from discord.ext import commands

from rainbot.main import RainBot
from ..ext.command import group
from ..ext.utility import apply_vars


class Tags(commands.Cog):
    def __init__(self, bot: RainBot) -> None:
        self.bot = bot

    @group(6, invoke_without_command=True)
    async def tag(self, ctx: commands.Context) -> None:
        """**Manages custom commands (tags)**

        This command allows you to create, remove, and list custom commands, also known as tags.
        When a tag is created, you can invoke it with `{prefix}tagname`.

        **Subcommands:**
        - `create` - Creates a new tag.
        - `remove` - Removes an existing tag.
        - `list` - Lists all available tags.
        """
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="tag")

    @tag.command()
    async def create(
        self, ctx: commands.Context, name: str, *, value: commands.clean_content
    ) -> None:
        """**Creates a new tag**

        This command creates a custom command (tag) with a specified name and value.

        **Usage:**
        `{prefix}tag create <name> <value>`

        **<name>:**
        The name of the tag. This will be used to invoke the command.

        **<value>:**
        The content that the bot will send when the tag is used. This can be simple text, a link, or even a JSON embed.

        **Examples:**
        - `{prefix}tag create hello Hi! I am the bot responding!`
        - `{prefix}tag create info Welcome to our server! Please read the rules in #rules.`

        For more complex usage, such as creating embeds, refer to the [documentation](https://github.com/fourjr/rainbot/wiki/Tags).
        """
        if value.startswith("http"):
            if value.startswith("https://hastebin.cc") and "raw" not in value:
                value = "https://hastebin.cc/raw/" + value[18:]

            async with self.bot.session.get(value) as resp:
                value = await resp.text()

        if name in [i.qualified_name for i in list(self.bot.commands)]:
            await ctx.send("Name is already a pre-existing bot command")
        else:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$push": {"tags": {"name": name, "value": value}}}
            )
            await ctx.send(f"Tag `{name}` created.")

    @tag.command()
    async def remove(self, ctx: commands.Context, name: str) -> None:
        """**Removes a tag**

        This command removes a custom command (tag) from the server.

        **Usage:**
        `{prefix}tag remove <name>`

        **<name>:**
        The name of the tag to remove.

        **Example:**
        `{prefix}tag remove hello`
        """
        await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"tags": {"name": name}}})
        await ctx.send(f"Tag `{name}` removed.")

    @tag.command(name="list")
    async def list_(self, ctx: commands.Context) -> None:
        """**Lists all tags**

        This command displays a list of all custom commands (tags) available on the server.

        **Usage:**
        `{prefix}tag list`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        tags = [i.name for i in guild_config.tags]

        if tags:
            await ctx.send("Tags: " + ", ".join(tags))
        else:
            await ctx.send("No tags saved")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.author.bot and message.guild:
            ctx = await self.bot.get_context(message)
            # This check is to ensure that the message is a command-like invocation.
            if not ctx.prefix or not ctx.invoked_with:
                return

            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            tags = [i.name for i in guild_config.tags]

            if ctx.invoked_with in tags:
                tag = guild_config.tags.get_kv("name", ctx.invoked_with)
                user_input = message.content.replace(
                    f"{ctx.prefix}{ctx.invoked_with}", "", 1
                ).strip()
                await ctx.send(
                    **self.format_message(tag.value, message, user_input),
                    allowed_mentions=discord.AllowedMentions.none(),
                )

    def apply_vars_dict(
        self, tag: Dict[str, Union[Any]], message: discord.Message, user_input: str
    ) -> Dict[str, Union[Any]]:
        for k, v in tag.items():
            if isinstance(v, dict):
                tag[k] = self.apply_vars_dict(v, message, user_input)
            elif isinstance(v, str):
                tag[k] = apply_vars(self.bot, v, message, user_input)
            elif isinstance(v, list):
                tag[k] = [self.apply_vars_dict(_v, message, user_input) for _v in v]
            if k == "timestamp":
                tag[k] = v[:-1]
        return tag

    def format_message(
        self, tag: str, message: discord.Message, user_input: str
    ) -> Dict[str, Union[Any]]:
        updated_tag: Dict[str, Union[Any]]
        try:
            updated_tag = json.loads(tag)
        except json.JSONDecodeError:
            # message is not embed
            tag = apply_vars(self.bot, tag, message, user_input)
            updated_tag = {"content": tag}
        else:
            # message is embed
            updated_tag = self.apply_vars_dict(updated_tag, message, user_input)

            if "embed" in updated_tag:
                updated_tag["embed"] = discord.Embed.from_dict(updated_tag["embed"])
            else:
                updated_tag = None
        return updated_tag


async def setup(bot: RainBot) -> None:
    await bot.add_cog(Tags(bot))

import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import create_embed
from utils.converters import MemberOrUser
from datetime import datetime, timezone


class Notes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.group(invoke_without_command=True)
    @has_permissions(level=2)
    async def note(self, ctx, member: MemberOrUser = None, *, note_text: str = None):
        f"""Keep private moderator notes about users for reference
        
        **Usage:** `{ctx.prefix}note <subcommand>` or `{ctx.prefix}note <user> <text>`
        **Examples:**
        • `{ctx.prefix}note @user Helpful member, active in chat`
        • `{ctx.prefix}note add @user Previously warned for spam`
        • `{ctx.prefix}note list @user` (view all notes for user)
        • `{ctx.prefix}note remove 5` (delete note #5)
        
        Notes are private to moderators and help track user behavior.
        """
        if member is None:
            embed = create_embed(
                title="📝 Note Commands",
                description="Use `!note add <user> <note>` to add a note",
                color="info",
            )
            await ctx.send(embed=embed)
            return

        if note_text:
            await self.add_note(ctx, member, note_text)

    @note.command(name="add")
    @has_permissions(level=2)
    async def add_note(self, ctx, member: MemberOrUser, *, note_text: str):
        """Create a new moderator note for a specific user"""
        config = await self.db.get_guild_config(ctx.guild.id)
        notes = config.get("notes", [])

        case_number = (notes[-1]["case_number"] + 1) if notes else 1

        note_entry = {
            "case_number": case_number,
            "member_id": str(member.id),
            "moderator_id": str(ctx.author.id),
            "note": note_text,
            "date": datetime.now(timezone.utc).isoformat(),
        }

        notes.append(note_entry)
        await self.db.update_guild_config(ctx.guild.id, {"notes": notes})

        embed = create_embed(
            title="✅ Note Added",
            description=f"Note #{case_number} added for {member.mention}: {note_text}",
            color="success",
        )
        await ctx.send(embed=embed)

    @note.command(name="remove", aliases=["delete", "del"])
    @has_permissions(level=2)
    async def remove_note(self, ctx, case_number: int):
        """Delete a specific note using its case number"""
        config = await self.db.get_guild_config(ctx.guild.id)
        notes = config.get("notes", [])

        note_to_remove = None
        for i, note in enumerate(notes):
            if note.get("case_number") == case_number:
                note_to_remove = notes.pop(i)
                break

        if not note_to_remove:
            embed = create_embed(
                title="❌ Note Not Found",
                description=f"Note #{case_number} doesn't exist",
                color="error",
            )
            await ctx.send(embed=embed)
            return

        await self.db.update_guild_config(ctx.guild.id, {"notes": notes})

        embed = create_embed(
            title="✅ Note Removed",
            description=f"Note #{case_number} has been removed",
            color="success",
        )
        await ctx.send(embed=embed)

    @note.command(name="list", aliases=["view"])
    @has_permissions(level=2)
    async def list_notes(self, ctx, member: MemberOrUser):
        """Display all moderator notes for a specific user"""
        config = await self.db.get_guild_config(ctx.guild.id)
        notes = config.get("notes", [])

        user_notes = [note for note in notes if note.get("member_id") == str(member.id)]

        if not user_notes:
            embed = create_embed(
                title="📝 No Notes",
                description=f"{member.mention} has no notes",
                color="info",
            )
            await ctx.send(embed=embed)
            return

        embed = create_embed(title=f"📝 Notes for {member}", color="info")

        for note in user_notes:
            moderator = ctx.guild.get_member(int(note.get("moderator_id", 0)))
            mod_name = moderator.mention if moderator else "Unknown"

            embed.add_field(
                name=f"Note #{note.get('case_number')} - {note.get('date', 'Unknown')}",
                value=f"**Moderator:** {mod_name}\n**Note:** {note.get('note', 'No content')}",
                inline=False,
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Notes(bot))

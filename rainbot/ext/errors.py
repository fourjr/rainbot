from typing import List

import discord
from discord.ext.commands import CheckFailure


class Underleveled(CheckFailure):
    """Exception raised when user's level does not meet the appropriate level"""

    pass


class BotMissingPermissionsInChannel(CheckFailure):
    """Exception raised when the bot lacks permissions in a channel to run command.
    Modified of commands.BotMissingPermissions

    Attributes
    -----------
    missing_perms: :class:`list`
        The required permissions that are missing.
    """

    def __init__(self, missing_perms: List[str], channel: discord.TextChannel, *args: list):
        self.missing_perms = missing_perms

        missing = [
            perm.replace("_", " ").replace("guild", "server").title() for perm in missing_perms
        ]

        if len(missing) > 2:
            fmt = "{}, and {}".format(", ".join(missing[:-1]), missing[-1])
        else:
            fmt = " and ".join(missing)
        message = "Bot requires {} permission(s) in #{}.".format(fmt, channel.name)
        super().__init__(message, *args)

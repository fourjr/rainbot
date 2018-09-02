from discord.ext.commands import CheckFailure


class Underleveled(CheckFailure):
    """Exception raised when user's level does not meet the appropriate level"""
    pass

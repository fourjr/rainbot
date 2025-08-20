import os
from enum import Enum


class Environment(Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Config:
    def __init__(self):
        self.environment = Environment(os.getenv("ENVIRONMENT", "development"))
        self.is_development = self.environment == Environment.DEVELOPMENT

        class Bot:
            def __init__(self):
                self.token = os.getenv("token")
                self.default_prefix = os.getenv("DEFAULT_PREFIX", "!!")
                self.max_messages = int(os.getenv("MAX_MESSAGES", 1000))

        class Database:
            def __init__(self):
                self.uri = os.getenv("mongo")
                self.name = os.getenv("DATABASE_NAME", "rainbot")
                self.server_selection_timeout = int(
                    os.getenv("SERVER_SELECTION_TIMEOUT_MS", 5000)
                )
                self.connection_timeout = int(os.getenv("CONNECTION_TIMEOUT_MS", 10000))
                self.max_pool_size = int(os.getenv("MAX_POOL_SIZE", 100))
                self.min_pool_size = int(os.getenv("MIN_POOL_SIZE", 10))

        class Channels:
            def __init__(self):
                self.owner_log_channel = (
                    int(os.getenv("owner_log_channel_id", 0))
                    if os.getenv("owner_log_channel_id")
                    else None
                )
                self.guild_join_channel = (
                    int(os.getenv("guild_join_channel_id", 0))
                    if os.getenv("guild_join_channel_id")
                    else None
                )
                self.guild_leave_channel = (
                    int(os.getenv("guild_remove_channel_id", 0))
                    if os.getenv("guild_remove_channel_id")
                    else None
                )
                self.error_channel = (
                    int(os.getenv("error_channel_id", 0))
                    if os.getenv("error_channel_id")
                    else None
                )

        class Api:
            def __init__(self):
                self.moderation_api_url = os.getenv("MODERATION_API_URL")

        class Logging:
            def __init__(self):
                self.level = os.getenv("LOG_LEVEL", "INFO")
                self.file_path = os.getenv("LOG_FILE_PATH", "logs/rainbot.log")
                self.max_file_size = int(
                    os.getenv("LOG_MAX_FILE_SIZE", 10485760)
                )  # 10MB
                self.backup_count = int(os.getenv("LOG_BACKUP_COUNT", 5))

        # Parse owner IDs
        owners_str = os.getenv("owners", "")
        self.owner_ids = (
            [int(id.strip()) for id in owners_str.split(",") if id.strip().isdigit()]
            if owners_str
            else []
        )

        self.bot = Bot()
        self.database = Database()
        self.channels = Channels()
        self.api = Api()
        self.logging = Logging()


config = Config()

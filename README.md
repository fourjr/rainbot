# 🤖 rainbot

A powerful, feature-rich Discord moderation bot with advanced automod, comprehensive logging, and user-friendly configuration.

[![Discord](https://img.shields.io/discord/733702521893289985?color=7289DA&label=Support%20Server&logo=discord&logoColor=white)](https://discord.gg/eXrDpGS)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.5.3-blue.svg)](https://github.com/Rapptz/discord.py)

## ✨ Features

### 🛡️ **Moderation**
- **Manual Moderation**: Kick, ban, mute, warn, and tempban commands
- **Advanced Auto-moderation**: Spam detection, invite blocking, bad word filtering
- **NSFW Detection**: AI-powered image analysis
- **Mass Mention Protection**: Prevent mention spam
- **Caps Lock Detection**: Automatic moderation of excessive caps
- **Duplicate Message Detection**: Prevent message spam

### 📝 **Logging System**
- **Comprehensive Logging**: Track all server activity
- **Moderation Logs**: Record all moderation actions
- **User Activity**: Member joins, leaves, role changes
- **Message Logs**: Edits, deletions, and reactions
- **Voice Activity**: Join, leave, move, and mute events
- **Server Changes**: Role, channel, and server updates

### ⚙️ **Configuration**
- **Interactive Setup**: User-friendly setup wizard
- **Permission Levels**: Granular permission system
- **Custom Commands**: Create server-specific commands
- **Reaction Roles**: Easy role assignment system
- **Giveaways**: Built-in giveaway system
- **Tags System**: Quick response system

### 🎯 **User Experience**
- **Rich Embeds**: Beautiful, informative responses
- **Interactive Menus**: Easy-to-use interface
- **Smart Help System**: Context-aware help commands
- **Error Handling**: User-friendly error messages
- **Statistics**: Detailed bot and server statistics

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- MongoDB database
- Discord Bot Token

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/fourjr/rainbot.git
   cd rainbot
   ```

2. **Use the deployment script (recommended)**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh install
   ```

3. **Or install manually**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```env
   token=your_discord_bot_token_here
   mongo=your_mongodb_connection_string
   owners=comma,separated,discord_user_ids  # e.g., 123,456
   error_channel_id=
   owner_log_channel_id=
   guild_join_channel_id=
   guild_remove_channel_id=
   dev_guild_id=
   DEBUG=false
   LOG_LEVEL=INFO
   ALLOW_EXEC_IN_PROD=false
   ```

5. **Run the bot**
   ```bash
   ./deploy.sh run
   # Or manually: python bot.py
   ```

## 🛠️ Setup System

The setup system provides an interactive way to configure rainbot for your server. Here's what each setup command does:

### `!setup` - Main Setup Menu
Shows the main setup menu with all available options:
- **Quick Setup** - Basic configuration
- **Advanced Setup** - Detailed configuration  
- **Auto-moderation** - Configure automod
- **Logging** - Set up logging channels
- **Permissions** - Configure permission levels
- **View Current** - See current settings

### `!setup quick` - Quick Setup Wizard
A step-by-step wizard that guides you through basic configuration:

1. **Command Prefix**: Choose your preferred prefix (e.g., `!`, `?`, `>`, `r!`)
2. **Mute Role**: Automatically creates a "Muted" role with proper permissions
3. **Moderation Logs**: Creates a channel for logging moderation actions

**What it configures:**
- Sets the command prefix for your server
- Creates and configures a mute role with proper channel permissions
- Sets up a moderation log channel
- Configures basic logging for bans, kicks, mutes, and warnings

### `!setup automod` - Auto-moderation Configuration
Interactive setup for automatic moderation features:

**Available Features:**
- **🔄 Spam Detection**: Prevents message spam
- **🔗 Invite Links**: Blocks Discord invite links
- **🤬 Bad Words**: Filters inappropriate content
- **📢 Mass Mentions**: Prevents mention spam
- **🔊 Caps Lock**: Moderates excessive caps
- **🖼️ NSFW Images**: Detects inappropriate images
- **📝 Duplicate Messages**: Prevents message repetition

### `!setup logging` - Logging Channel Setup
Configure channels for different types of logging:

**Log Types:**
- **👥 Member Joins/Leaves**: Track member activity
- **🔨 Moderation Actions**: Log all moderation
- **💬 Message Edits/Deletes**: Track message changes
- **🎭 Role Changes**: Monitor role updates
- **🔊 Voice Activity**: Track voice channel activity
- **🛡️ Server Updates**: Monitor server changes

### `!setup permissions` - Permission Level Setup
Configure permission levels for your server:

**Permission Levels:**
- **Level 0**: Everyone - Basic commands
- **Level 1**: Helper - Basic moderation
- **Level 2**: Moderator - Kick, warn, mute
- **Level 3**: Senior Moderator - Ban, tempban
- **Level 4**: Admin - All moderation
- **Level 5**: Senior Admin - Server management
- **Level 6**: Server Manager - Full control

**How to set permissions:**
```
!setpermlevel <level> <role>
Example: !setpermlevel 2 @Moderator
```

## 📋 Commands

### 🔧 **Setup Commands**
- `!setup` - Interactive setup wizard
- `!setup quick` - Quick basic setup
- `!setup automod` - Configure auto-moderation
- `!setup logging` - Set up logging channels
- `!setup permissions` - Configure permission levels
- `!viewconfig` - View current configuration
- `!importconfig <url>` - Import configuration from URL
- `!resetconfig` - Reset to default settings

### 🛡️ **Moderation Commands**
- `!kick <user> [reason]` - Kick a user
- `!ban <user> [duration] [reason]` - Ban a user
- `!tempban <user> <duration> [reason]` - Temporarily ban a user
- `!mute <user> <duration> [reason]` - Mute a user
- `!warn <user> <reason>` - Warn a user
- `!unban <user_id>` - Unban a user
- `!unmute <user>` - Unmute a user

### 📊 **Utility Commands**
- `!help [command]` - Show help information
- `!about` - Bot information and statistics
- `!server` - Server information
- `!user <user>` - User information
- `!ping` - Check bot latency
- `!stats` - Detailed bot statistics
- `!invite` - Get bot invite link

### 🎭 **Role Management**
- `!role <user> <role>` - Add/remove role from user
- `!reactionrole` - Set up reaction roles
- `!autorole <role>` - Set automatic role assignment

### 🎉 **Giveaways**
- `!gstart <duration> <winners> <prize>` - Start a giveaway
- `!gend <message_id>` - End a giveaway
- `!greroll <message_id>` - Reroll giveaway winners

## ⚙️ Configuration

### Permission Levels
- **Level 0**: Everyone - Basic commands
- **Level 1**: Helper - Basic moderation
- **Level 2**: Moderator - Kick, warn, mute
- **Level 3**: Senior Moderator - Ban, tempban
- **Level 4**: Admin - All moderation
- **Level 5**: Senior Admin - Server management
- **Level 6**: Server Manager - Full control

### Auto-moderation Settings
- **Spam Detection**: Prevent message spam
- **Invite Blocking**: Block Discord invite links
- **Bad Word Filter**: Filter inappropriate content
- **Mass Mentions**: Prevent mention spam
- **Caps Lock**: Moderate excessive caps
- **NSFW Detection**: Detect inappropriate images
- **Duplicate Messages**: Prevent message repetition

### Logging Channels
- **Moderation Logs**: All moderation actions
- **User Logs**: Member joins, leaves, role changes
- **Message Logs**: Message edits, deletions
- **Voice Logs**: Voice channel activity
- **Server Logs**: Server configuration changes

## 🔧 Advanced Configuration

### Custom Commands
Create server-specific commands with variables:
```
!addcommand welcome Welcome {user} to {server}!
```

### Reaction Roles
Set up automatic role assignment:
```
!reactionrole add 🎮 Gamer
```

### Word Filter
Manage bad word filtering:
```
!filter add badword
!filter remove badword
```

### Canned Responses
Set up quick response templates:
```
!setcanned welcome Welcome to our server!
```

## 🛠️ Development

### Project Structure
```
rainbot/
├── bot.py              # Main bot file
├── config.py           # Configuration settings
├── requirements.txt    # Python dependencies
├── deploy.sh           # Deployment script
├── cogs/              # Bot modules
│   ├── moderation.py  # Moderation commands
│   ├── utils.py       # Utility commands
│   ├── setup.py       # Setup commands
│   ├── logs.py        # Logging system
│   └── ...
├── ext/               # Extensions
│   ├── command.py     # Command decorators
│   ├── database.py    # Database management
│   ├── utility.py     # Utility functions
│   └── ...
└── stubs/             # Type stubs
```

### Adding New Features
1. Create a new cog in the `cogs/` directory
2. Use the `@command()` decorator for commands
3. Add proper error handling and user feedback
4. Update documentation

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📊 Statistics

- **Servers**: 1000+
- **Users**: 500,000+
- **Commands Processed**: 1M+
- **Uptime**: 99.9%

## 🔗 Links

- **[Invite Bot](https://discord.com/oauth2/authorize?client_id=372748944448552961&scope=bot&permissions=2013785334)** - Add to your server
- **[Support Server](https://discord.gg/zmdYe3ZVHG)** - Get help and support
- **[Documentation](https://github.com/fourjr/rainbot/wiki)** - Detailed guides
- **[GitHub](https://github.com/fourjr/rainbot)** - Source code

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper
- [MongoDB](https://www.mongodb.com/) - Database
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal output
- [TensorFlow](https://tensorflow.org/) - AI/ML capabilities

## 🆘 Support

If you need help:
1. Check the [documentation](https://github.com/fourjr/rainbot/wiki)
2. Join our [support server](https://discord.gg/zmdYe3ZVHG)
3. Create an [issue](https://github.com/fourjr/rainbot/issues) on GitHub



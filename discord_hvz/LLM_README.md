 # Discord-HvZ Bot — Functional Overview
 
 This repository implements a self-hosted Discord bot to run a Humans vs. Zombies (HvZ) game for a Discord server, typically at a university. The bot manages registration, tag reporting, player roles, game announcements, live game statistics/visualizations, optional Google Sheets export, and a configurable chatbot system for workflows such as registration and tag logging.
 
 This document describes how the system functions, its major components, data flows, and how they fit together. It intentionally focuses on capabilities and architecture rather than code-level details.
 
 
 ## High-Level Architecture
 
 - **Runtime:** Python application using Pycord (`discord.py`-compatible) with slash commands, buttons, and interactions.
 - **Entry point:** `discord_hvz/__main__.py` and `discord_hvz/main.py`.
 - **Bot type:** A subclassed `discord.ext.commands.Bot` called `HVZBot` that loads multiple cogs for features.
 - **Persistence:** SQLite database (path configurable in `config.yml`). Schema is derived from `scripts.yml` (chatbot scripts) plus required system tables/columns.
 - **Sheets integration (optional):** Google Sheets API updates for tables defined in the configuration.
 - **Configuration:** Validated by Pydantic from `config.yml`. Additional chatbot scripting and schema is loaded from `scripts.yml`.
 - **Extensibility:** Feature cogs: `commands`, `buttons`, `display`, `item_tracker`, and `chatbot`.
 
 
 ## Configuration and Boot
 
 - The bot loads environment variables (notably `TOKEN` from `.env`).
 - `config.yml` is parsed and validated into a `HVZConfig` model in `discord_hvz/config.py`.
   - Critical settings include:
     - `server_id`: Discord server (guild) to operate on.
     - `channel_names`: Maps required logical channels to actual names: `tag-announcements`, `report-tags`, `zombie-chat`, `bot-output` (optional).
     - `role_names`: Maps logical roles to Discord roles: `zombie`, `human`, `player`.
     - `timezone`: IANA name (or offset) used for scheduling and timestamps.
     - Feature toggles: `registration`, `tag_logging`, `silent_oz`, `google_sheet_export`.
     - `sheet_id`/`sheet_names`: Google Sheets export destination and tabs.
     - `database_path`: SQLite database location (file or folder, resolved at runtime).
     - `sheet_columns`: Optional ordering hints for exported columns.
 - `scripts.yml` is parsed by `discord_hvz/chatbot/script_models.py` to define chatbot workflows and drive database schema creation.
 - On `HVZBot` startup (`main.py`):
   - The bot connects to Discord with intents set to `Intents.all()`.
   - The correct guild is found via `server_id`.
   - The bot resolves channels and roles by name.
   - The database (`HvzDb`) is initialized with schema derived from the script model (and system-required columns). Missing tables/columns are created as needed.
   - The following extensions (cogs) are loaded: `buttons`, `chatbot`, `commands`, `display`, `item_tracker`.
   - Optional `bot-output` channel acts as a log sink for bot messages if configured.
 
 
 ## Data Model and Persistence
 
 - **Database:** SQLite file managed via SQLAlchemy, wrapped by `discord_hvz/database.py` (`HvzDb`).
 - **Schema source:** The chatbot scripts (`scripts.yml`) define one or more forms (scripts) with questions that map to table columns. The model enforces:
   - One table per script.
   - Each question has a `column` and optionally a `column_type` (strings default to text). Some critical tables/columns are enforced by the system regardless of `scripts.yml`.
 - **Core tables:**
   - `members`: Registered players with columns such as `id`, `name`, `discord_name`, `nickname`, `faction`, `tag_code`, `registration_time`, `oz`.
   - `tags`: Tag events with columns such as `tag_id` (auto-increment), `tagger_id`, `tagged_id`, `tag_time`, `report_time`, `revoked_tag`, plus friendly name/nickname copies for both parties.
   - `persistent_panels`: Tracks live display panels so they persist through restarts.
   - Additional tables can be introduced by `scripts.yml` (e.g., custom scripts) and by feature cogs (e.g., `items`).
 - **Helpers:** `HvzDb` exposes CRUD helpers (`add_row`, `get_row[s]`, `edit_row`, `delete_row`, `get_table`, `get_column_names`) and notifies Sheets when a managed table changes.
 
 
 ## Google Sheets Integration (Optional)
 
 - If `google_sheet_export` is enabled and `sheet_id`/`sheet_names` are provided, a `SheetsInterface` (`discord_hvz/sheets.py`) is created.
 - On table changes (for tables defined by scripts), queued updates export the full table to the corresponding tab.
 - Credentials:
   - `credentials.json`: OAuth client secret placed in the bot’s root directory.
   - On first run, an OAuth flow saves `token.json` for reuse.
 - Export formatting:
   - The first row contains column headers.
   - Column order can be influenced by `sheet_columns` in `config.yml`. Missing columns are appended to the right.
 
 
 ## Core Runtime: The HVZBot
 
 - The `HVZBot` class in `discord_hvz/main.py` wraps the Discord bot and coordinates cogs, database, roles, and channels.
 - Guild events handled:
   - `on_ready`: Resolves guild, prefetches members/channels/roles, sets up role/channel mappings, and logs startup.
   - `on_member_update`: Synchronizes database `faction` and `nickname` when roles/nicknames change.
   - Centralized error handling for application commands.
 - Convenience methods:
   - `str_to_channel`, `str_to_role` for resolving configured names.
   - `announce_tag()` posts formatted tag announcements to `tag-announcements` (respects `silent_oz`).
   - `get_cog_startup_data()` provides startup configuration objects to cogs (e.g., pre-parsed scripts, config checkers).
 
 
 ## Feature Cogs
 
 ### 1) Admin and Player Commands (`discord_hvz/commands.py`)
 
 Slash command sets are grouped and restricted to the configured guild.
 
 - Member management (`/member` group):
   - `/member register <discord.Member>`
     - Starts the registration chatbot on behalf of a selected Discord user (the command invoker hosts the conversation). Prevents duplicate registration.
   - `/member delete` (by selected member or ID):
     - Removes a player from the `members` table and strips `human`/`zombie`/`player` roles if the Discord user is present.
   - `/member edit <member> <attribute> <value>`:
     - Directly edits a field in the `members` row. No validation beyond column existence.
   - `/member list`:
     - Paginates all `members` with mention/name/nickname/email.
 - Tag management (`/tag` group):
   - `/tag create <discord.Member>`
     - Starts the tag logging chatbot on behalf of the given member (the selected member is the tagger).
   - `/tag delete <tag_id>`
     - Deletes a tag and, if no other active tag makes the `tagged_id` a zombie, reverts them to human.
   - `/tag edit <tag_id> <attribute> <value>`
     - Edits one field of an existing tag and triggers tag-related updates.
   - `/tag revoke <tag_id>` and `/tag restore <tag_id>`
     - Toggles `revoked_tag`. Revoking can revert roles to human if appropriate; restoring re-applies zombie roles.
   - `/tag list`
     - Paginates all tags with summaries.
 - Bot configuration (`/config <setting> [choice]`):
   - Views or toggles select `config` flags at runtime. Changes are persisted back into `config.yml` for simple types.
 - Player utility commands:
   - `/code` returns the invoking user’s `tag_code` privately.
   - `/tag_tree` renders a textual “zombie family tree,” derived from `tags` and role membership.
 - Lifecycle:
   - `/shutdown [force]` gracefully closes the bot, optionally canceling active chatbots.
 - OZ support:
   - `/oz <member> [True|False]` views/sets “original zombie” override allowing access to zombie channels while human, by channel permission overwrites.
 - Config file updates via DM:
   - `/download_config` DMs `config.yml` and `scripts.yml` to the admin; replies with edited files attached will overwrite the bot-side files (filenames must match exactly).
 
 
 ### 2) Buttons and Persistent “Postable” Buttons (`discord_hvz/buttons.py`)
 
 - The bot exposes a slash command to post messages with persistent buttons that launch chatbots.
 - Buttons are instances of `HVZButton` with unique `custom_id`s; they survive restarts via a persistent view.
 - Default button functions include `register` and `tag_log`, but more are auto-generated by the chatbot system (see below).
 - The `/post_button`-style command is dynamically registered after the cog’s `on_ready` to include all current postable buttons.
 
 
 ### 3) Display Panels and Game Plot (`discord_hvz/display.py`)
 
 - Provides live-updating, embeddable “panels” with game stats. Panels persist across restarts via `persistent_panels`.
 - Admin commands:
   - `/post_panel` to post a composite panel of selectable elements. Elements include:
     - `HumanElement`: Current count of `human` role members.
     - `ZombieElement`: Current count of `zombie` role members (optionally excludes OZ from count display if `silent_oz`).
     - `PlayerElement`: Total with `player` role.
     - `PlayersTodayElement`: New `members` registered in the last 24 hours.
     - `TagsTodayElement`: `tags` created in the last 24 hours.
     - `TagTreeElement`: The textual tag tree (trimmed to embed limits if needed).
   - `/game_plot` to post a panel with a time series chart showing Zombies vs. Humans over time.
 - The chart is generated via QuickChart and cached on disk (`plots/latest_gameplot.png`). Data is derived from the database using pandas.
 - Panels self-refresh on relevant events (e.g., role changes or tag updates). Deleting the message automatically cleans up the corresponding persistent record.
 
 
 ### 4) Item Tracking (`discord_hvz/item_tracker.py`)
 
 - Adds an `items` table with auto-increment `id`, `name`, and `owner` (Discord user ID or 0 for storage).
 - Slash commands under `/item`:
   - `/item list [member]` lists items globally or for a specific player.
   - `/item create <name> [starting_player]` creates an item and optionally assigns it.
   - `/item delete <id>` deletes an item.
   - `/item delete_all [are_you_sure]` wipes the items table.
   - `/item transfer <id> <target_player>` hands off an item.
   - `/item take <id>` returns an item to storage.
   - `/item rename <id> <new_name>` renames an item.
 
 
 ### 5) Chatbot System (`discord_hvz/chatbot/*` and `chatbotprocessors/*`)
 
 A flexible, script-driven chatbot engine handles guided interactions like registration and tag logging.
 
 - Scripts are defined in `scripts.yml` and validated by `discord_hvz/chatbot/script_models.py` into a `ScriptFile` model with `ScriptDatas` and `QuestionDatas`.
 - Each script defines:
   - `kind`: Script identifier (e.g., `registration`, `tag_logging`).
   - `table`: Target DB table for the script’s responses.
   - `modal`: If `true`, uses Discord modals; if `false`, uses private threads plus buttons.
   - `beginning`/`ending`: Intro/outro texts.
   - `questions`: Prompt text, optional regex validation/rejection, optional processors, and optional `button_options`.
   - Optional `starting_processor` and `ending_processor` functions, by name, referring to `chatbotprocessors` registry.
 - On bot startup, `ChatBotManager` loads and registers:
   - A postable button for each script (label/color configurable) so admins can post launchers easily.
   - Per-script `ConfigChecker`s (backed by `config.yml` booleans) so scripts can be toggled without code changes.
 - Conversation flow:
   - For non-modal scripts, the bot opens a private thread with the invoking user.
   - The chatbot sends the intro and the first question. Users answer by typing or pressing option buttons.
   - Each response may run a “question processor” to transform/validate input (e.g., tag code lookup -> member ID).
   - After the last question (or on entering Review), the user can submit, modify specific answers, or cancel.
   - On submit, the `ending_processor` may finalize records and apply side effects (e.g., assign roles, send announcements, dispatch `tag_changed`).
 - Critical built-in workflows (default processors in `chatbotprocessors/default_*`):
   - `registration`:
     - Prevents duplicate registration, records member fields (including generated `tag_code`), sets `player` and `human` roles.
   - `tag_logging`:
     - Validates the victim’s tag code, records `tag_time` (parsing free text, supporting “yesterday” semantics), sets `tagged_id` and updates names/nicknames.
     - Applies roles (`zombie` added, `human` removed), updates `members.faction`, triggers `tag_changed`, and posts an announcement to `tag-announcements`.
 - Processors live in `chatbotprocessors/` and return database-storable values. Raising a `ValueError` prompts the user to correct their answer; any other exception gracefully aborts the chatbot.
 - The system enforces critical schema using `REQUIRED_COLUMNS` from `default_script_processors.py`.
 
 
 ## Game Mechanics Implemented
 
 - **Registration:**
   - Via slash command or a postable button that launches the registration chatbot. Stores player identity fields and `tag_code`, sets roles.
 - **Tag Reporting:**
   - Zombies collect a victim’s `tag_code`. The tagger (or an admin on their behalf) launches the tag logging chatbot, which records the event and updates roles and announcements.
 - **Roles and Permissions:**
   - `player`: Assigned to all registered players.
   - `human` / `zombie`: Reflect current state. OZ (Original Zombie) can be flagged to access zombie channels while human.
   - Channel access (e.g., `report-tags`, `zombie-chat`) depends on roles and, for OZ, per-user channel overwrites managed by the `/oz` command.
 - **Announcements and Displays:**
   - Tag announcements with counts of humans/zombies and time of tag.
   - Live dashboards and a time series plot of player counts over time.
 - **Exports:**
   - Members and tags can be exported to Google Sheets for broader visibility and archival.
 
 
 ## Utilities and Supporting Features
 
 - `discord_hvz/utilities.py` provides helpers for:
   - `make_tag_code()` unique tag code generation.
   - Pagination of long responses to stay under Discord message limits.
   - Building the zombie tag tree by walking the `tags` table and current roles.
   - Throttling batched actions (e.g., panel refresh) to avoid rate limits.
   - Formatting Pydantic validation errors for readability.
 - Error handling and logging use `loguru`, with error levels, backtraces, and optional channel sink.
 
 
 ## Operational Requirements
 
 - Discord setup:
   - Create `zombie`, `human`, and `player` roles.
   - Create `tag-announcements`, `report-tags`, `zombie-chat` channels; optionally `bot-output` for logs.
   - Ensure the bot user is on the server with permissions to read/write channels and manage roles.
 - Files:
   - `.env` with `TOKEN='your_bot_token'`.
   - `config.yml` with your server/channel/role IDs and other options.
   - `scripts.yml` defining chatbot flows. The project expects it in the project root (same folder as `config.yml`).
   - If Sheets export is used: `credentials.json` in the root; the bot will create `token.json` after OAuth.
 - Database:
   - `database_path` in `config.yml` controls where the SQLite file lives. Missing files/tables are created automatically.
   - Changing required schema after data exists may require deleting the DB and restarting (the bot warns in such cases).
 
 
 ## Safety and Failure Modes
 
 - Many commands catch `ValueError` to provide user-friendly feedback.
 - Configuration and scripts are strictly validated; misconfiguration causes a human-readable error message and early exit.
 - The bot avoids acting on events from other guilds by checking against `server_id`.
 - If Sheets updates fail, the bot logs the exception but continues operating.
 - Chatbots time out and are cleaned up if left idle (scheduled removal tasks).
 
 
 ## Extensibility Points
 
 - Add or modify chatbot flows in `scripts.yml`.
   - Use `chatbotprocessors/default_question_processors.py` and `default_script_processors.py` for examples.
   - You can place custom processors in `chatbotprocessors/` and reference them by name in `scripts.yml`.
 - Add new features as cogs (see `buttons`, `display`, `item_tracker`, `commands`) and load them from `main.py`.
 - Add panel elements by subclassing the `PanelElement` pattern in `display.py`.
 - Extend exports by mapping more tables in `config.yml.sheet_names`.
 
 
 ## Typical End-to-End Flows
 
 - Registration:
   1) Admin posts a registration button or runs `/member register @User`.
   2) User completes the registration chatbot.
   3) Bot writes a row in `members`, assigns roles `player` and `human`.
   4) Optional: Sheets export updates the `Members` sheet.
 
 - Tagging:
   1) A zombie obtains a victim’s `tag_code`.
   2) The tagger starts the tag logging chatbot (from button or `/tag create @Tagger`).
   3) Victim is resolved via tag code; time is parsed; a tag row is added.
   4) Bot updates roles (victim becomes `zombie`) and posts an announcement.
   5) Optional: Sheets export updates the `Tags` sheet; panels refresh.
 
 
 ## Dependencies and Packaging
 
 - Managed with Poetry (`pyproject.toml`). Key dependencies:
   - `py-cord`: Discord interactions.
   - `SQLAlchemy`, `pandas`: Persistence and analytics.
   - `loguru`: Logging.
   - Google API libraries for Sheets export.
   - `pydantic`, `pydantic-yaml`, `ruamel.yaml`: Configuration and script validation.
   - `quickchart-io`: Chart generation.
 - CLI entry points (`tool.poetry.scripts`):
   - `discord_hvz`, `main`, `display` all point to `discord_hvz:main`.
 
 
 ## Notes for Another LLM
 
 - The bot’s behavior is data-driven by `config.yml` and `scripts.yml`. Always consult these files to understand active flows and schema.
 - Channel/role names in `config.yml` must match exactly those on the target server, or startup will raise clear errors.
 - The chatbot system coordinates most side effects; look for `starting_processor`/`ending_processor` and required columns to infer exactly what a script will do.
 - The database wrapper will auto-create the declared schema; updates to required columns after a DB already exists may need manual intervention (delete or migrate the DB).
 - For any feature tied to Sheets, ensure credentials are present; otherwise leave `google_sheet_export` disabled.
 
 
 ## File Map — Key Modules
 
 - `discord_hvz/main.py`: Bot startup, logging, event hooks, extension loading, announce helpers.
 - `discord_hvz/config.py`: Pydantic config model, runtime updates to simple fields persist back to `config.yml`.
 - `discord_hvz/database.py`: SQLite schema management, CRUD helpers, Sheets integration triggers.
 - `discord_hvz/commands.py`: Slash commands for admins/players (registration proxy, tag management, OZ, config, tag tree, shutdown, DM config updater).
 - `discord_hvz/buttons.py`: Persistent button infrastructure and posting command.
 - `discord_hvz/display.py`: Live panels and time series chart generation.
 - `discord_hvz/item_tracker.py`: Optional items feature with CRUD slash commands.
 - `discord_hvz/chatbot/`: Chatbot engine, modal support, thread management, script parsing/validation, and utilities.
 - `chatbotprocessors/`: Built-in processors and required column definitions backing critical flows.
 
 
 ---
 If you need more detail on how to customize the game workflows, open `scripts.yml` and `chatbotprocessors/` to see how questions map to database columns and how processors transform user inputs into game actions.
 

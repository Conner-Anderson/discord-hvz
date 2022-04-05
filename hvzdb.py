from __future__ import annotations
import discord, sheets
import os.path
from dataclasses import dataclass, field, InitVar
from typing import List, Union, Dict, TYPE_CHECKING, Any, ClassVar
import copy
import functools

from sqlalchemy.engine.mock import MockConnection

if TYPE_CHECKING:
    from discord_hvz import HVZBot
from datetime import datetime

import sqlalchemy
from sqlalchemy.engine import Row
from sqlalchemy import create_engine, MetaData, event, text
from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy import insert, select, delete, update
from sqlalchemy import func, cast, and_
from sqlalchemy.exc import NoSuchTableError, CompileError

from config import config, ConfigError

from loguru import logger

def dump(obj):
    """Prints the passed object in a very detailed form for debugging"""
    for attr in dir(obj):
        try:
            print("obj.%s = %r" % (attr, getattr(obj, attr)))
        except Exception:
            print('TYPE ERROR')

@dataclass
class HvzDb:
    engine: sqlalchemy.engine.Engine = field(init=False)
    metadata_obj: MetaData = field(init=False, default_factory=MetaData)
    tables: Dict[str, Table] = field(init=False, default_factory=dict)
    sheet_interface: sheets.SheetsInterface = field(init=False, default=None)
    filename: str = 'hvzdb.db'
    database_config: Dict[str, Dict[str, str]] = field(init=False, default_factory=dict)

    # Table names that cannot be created in the config. Reserved for cogs / modules
    reserved_table_names: ClassVar[List[str]] = ['persistent_panels']

    required_columns: ClassVar[Dict[str, Dict[str, str]]] = {
        'members': {
            'ID': 'String',
            'Name': 'String',
            'Faction': 'String',
            'Tag_Code': 'String',
            'OZ': 'Boolean'
        },
        'tags': {
            'Tag_ID': 'Integer',
            'Tagger_ID': 'String',
            'Tagger_Name': 'String'
        }
    }

    valid_column_types: ClassVar[Dict[str, type]] = {
        'string': String,
        'integer': Integer,
        'incrementing_integer': Integer,
        'boolean': Boolean,
        'datetime': DateTime
    }

    
    def __post_init__(self):
        # TODO: Need to make sure the required tables are always created. Might be config-depended now...
        self.database_config: Dict[str, Dict[str, str]] = copy.deepcopy(config['database_tables'])
        self.engine = create_engine(f"sqlite+pysqlite:///{self.filename}", future=True)

        for table_name, column_dict in self.database_config.items():
            try:
                self.tables[table_name] = Table(table_name, self.metadata_obj, autoload_with=self.engine)
                continue
            except NoSuchTableError: pass
            logger.warning(f'Found a table called "{table_name}" in the config, but not in the database. Creating the table.')


            column_args = []
            # Add any required columns that are missing


            # Create Columns from the config
            for column_name, type_string in column_dict.items():
                column_args.append(self._create_column_object(column_name, type_string))

            if table_name in self.required_columns:
                required_columns_table = self.required_columns[table_name]
                for column_name, type_string in required_columns_table.items():
                    if column_name in column_dict:
                        continue
                    column_args.append(self._create_column_object(column_name, type_string))
                    logger.warning(f'The required column "{column_name}" was not found in the config for the table "{table_name}". Creating it.')

            self.tables[table_name] = Table(table_name.casefold(), self.metadata_obj, *column_args)

        self.metadata_obj.create_all(self.engine)

        # TODO: Find a way to not need this
        # Give each table a table_names tuple which is all column names
        for name, table in self.tables.items():
            selection = select(table)
            with self.engine.begin() as conn:
                result = conn.execute(selection)
                table.column_names = result.keys()

        if config['google_sheet_export'] == True:
            self.sheet_interface = sheets.SheetsInterface(self)

    def prepare_table(self, table_name: str, columns: Dict[str, Union[str, type]]) -> None:
        """
        Creates a new table in the database if there is none, and loads the table from the database if it exists already.
        """
        try:
            self.tables[table_name] = Table(table_name, self.metadata_obj, autoload_with=self.engine)
        except NoSuchTableError:
            logger.warning(
                f'Creating table "{table_name}" since it was not found in the database.')

            column_args = []
            # Create Columns from the config
            for column_name, column_type in columns.items():
                column_args.append(self._create_column_object(column_name, column_type))

            self.tables[table_name] = Table(table_name.casefold(), self.metadata_obj, *column_args)

        self.metadata_obj.create_all(self.engine)
        self.tables[table_name].column_names = columns.keys()

    def delete_table(self, table_name: str):
        self.tables[table_name].drop(bind=self.engine)
        logger.warning(f'Deleted tabled named {table_name}')


    def _table_updated(self, table: Union[Table, str]) -> None:
        """
        To be called whenever a function changes a table. This lets the Google Sheet update.
        :param table:
        :return:
        """
        try:
            if isinstance(table, Table): table_name = table.name
            else: table_name = table
            if table in self.database_config: # Only send to Sheets if the table is in config.yml
                self.sheet_interface.update_table(table_name)
        except Exception as e:
            # Allow sheet failure to silently pass for the user.
            logger.exception(f'The database failed to update to the Google Sheet with this error: {e}')


    def _create_column_object(self, column_name: str, column_type: Union[str, type]) -> Column:
        """
        Returns a Column object after forcing the name to lowercase and validating the type
        :param column_name:
        :param column_type: A string matching a valid column type
        :return: Column object
        """
        if not isinstance(column_type, str):
            if column_type in self.valid_column_types.items():
                column_type_object = column_type
            else:
                raise TypeError(f'column_type is an invalid type: {type(column_type)}')
        else:
            try:
                column_type_object = self.valid_column_types[column_type.casefold()]
            except KeyError:
                column_type_object = String

        kwargs = {}
        if column_type == 'incrementing_integer':
            kwargs = {'primary_key': True, 'nullable':False, 'autoincrement':True}

        return Column(column_name.casefold(), column_type_object, **kwargs)

    def __add_row(self, table, row):
        # Old function acting as an alias
        return self.add_row(table, row)

    def add_row(self, table_selection:str, input_row: Dict):
        table = self.tables[table_selection.casefold()]

        row = {}
        # Convert all column names to lowercase
        for k, i in input_row.items():
            row[k.casefold()] = i

        with self.engine.begin() as conn:
            result = conn.execute(table.insert().values(row))
            self._table_updated(table)
            return result




    def get_member(self, value, column: str = None) -> Row:
        """
        Returns a Row object that represents a single member in the database

        Parameters:
                member (int or user): A user id or a discord.abc.User object

        Returns:
                row (Row): Row object. Access rows in these ways: row.some_row, row['some_row']
        """
        if column is not None:
            search_value = value
            search_column = column.casefold()
        else:
            search_column = 'id'
            if isinstance(value, discord.abc.User):
                search_value = value.id
            else:
                search_value = value

        member_row = self.__get_row(self.tables['members'], self.tables['members'].c[search_column], search_value)
        return member_row

    def get_tag(self, value, column=None, filter_revoked=False):
        '''
        Returns a Row object that represents a single tag in the database

        Parameters:
                tag_id (int): A tag id, which you can find on the Tags Google sheet

        Returns:
                row (Row): Row object. Access rows in these ways: row.some_row, row['some_row']
        '''
        table = self.tables['tags']
        if column is not None:
            search_column = column
            if search_column not in table.column_names:
                raise ValueError(f'{search_column} not a column in {table}')
        else:
            search_column = 'Tag_ID'

        if filter_revoked is False:
            tag_row = self.__get_row(table, table.c[search_column], value)
        else:
            tag_row = self.__get_row(table, table.c[search_column], value,
                                     exclusion_column=table.c['Revoked_Tag'], exclusion_value=True)
        return tag_row

    def __get_row(self, table, search_column, search_value, exclusion_column=None, exclusion_value=None):
        '''
        Returns the first Row object where the specified value matches.
        Meant to be used within the class.

        Parameters:
                table (sqlalchemy.table): Table object
                column (sqlalchemy.column): Column object to search for value
                value (any): Value to search column for
                exclusion_column (sqlalchemy.column) Optional. Reject rows where this column equals exclusion_value
                exclusion_value (any) Optional. Required if exclusion_column is provided.

        Returns:
                row (Row): Row object. Access rows in these ways: row.some_row, row['some_row']
        '''
        selection = select(table).where(search_column == search_value)
        if (exclusion_column is not None):
            if exclusion_value is None:
                raise ValueError('No exclusion value provided.')
            selection = selection.where(exclusion_column != exclusion_value)
        with self.engine.begin() as conn:
            result_row = conn.execute(selection).first()
        if result_row is None:
            raise ValueError(f'Could not find a row where \"{search_column}\" is \"{search_value}\"')
        return result_row

    def get_table(self, table) -> List[Row]:
        """
        Returns a list of all members in the database

        Parameters:
                table (str): The name of the table to fetch. Lower case

        Returns:
                result (list[Row]): List of Rows. Rows are like tuples, but with dictionary
                                                keys. Like this: row['Name'] or row.Name
        """
        selection = select(self.tables[table])
        with self.engine.begin() as conn:
            result = conn.execute(selection).all()
            return result

    # Legacy method left in here for reference
    def get_column(self, table: str, column: str):
        # Returns the first column that matches. The column is a list.
        sql = f'SELECT {column} FROM {table}'
        cur = self.conn.cursor()

        output = cur.execute(sql).fetchall()

        return output

    def edit_member(self, member, column, value):
        """
        Edits an attribute of a member in the database

        Parameters:
                member (int or user): A user id or a discord.abc.User object
                column (str): A string matching the column to change. Case sensitive.
                value (any?): Value to change the cell to.

        Returns:
                result (bool): True if the edit was successful, False if it was not.
        """
        member_id = member
        if isinstance(member, discord.abc.User):
            member_id = member.id
        result = self._edit_row(
            self.tables['members'],
            self.tables['members'].c.id,
            member_id,
            column,
            value
        )
        return result

    def edit_tag(self, tag_id, column, value):
        """
        Edits an attribute of a tag in the database

        Parameters:
                tag_id (int or user): A tag ID
                column (str): A string matching the column to change. Case sensitive.
                value (any?): Value to change the cell to.

        Returns:
                result (bool): True if the edit was successful, False if it was not.
        """

        result = self._edit_row(
            self.tables['tags'],
            self.tables['tags'].c.tag_id,
            tag_id,
            column,
            value
        )
        return result

    def _edit_row(self, table: Table, search_column, search_value, target_column, target_value):
        updator = (
            update(table).where(search_column == search_value).
                values({target_column: target_value})
        )

        if target_column not in table.column_names:
            raise ValueError(f'{search_column} not a column in {table}')

        with self.engine.begin() as conn:
            result = conn.execute(updator)
        if result.rowcount > 0:
            self._table_updated(table)
            return True
        else:
            raise ValueError(f'\"{search_value}\" not found in \"{search_column}\" column.')

    def delete_member(self, member):
        member_id = member
        if isinstance(member, discord.abc.User):
            member_id = member.id

        self.delete_row(
            self.tables['members'],
            self.tables['members'].c.id,
            member_id
        )
        return

    def delete_tag(self, tag_id):
        table = self.tables['tags']
        self.delete_row(
            table,
            table.c.tag_id,
            tag_id
        )
        return

    def delete_row(self, table: Union[Table, str], search_column, search_value):
        if isinstance(table, str):
            try:
                table = self.tables[table]
            except KeyError:
                raise KeyError(f'{table} is not a table.') from None

        if search_column not in table.column_names:
            raise ValueError(f'{search_column} not a column in {table}')

        deletor = delete(table).where(table.c[search_column] == search_value)
        with self.engine.begin() as conn:
            result = conn.execute(deletor)
        if result.rowcount < 1:
            raise ValueError(f'Could not find rows where \"{search_column}\" is \"{search_value}\"')
        self._table_updated(table)
        return True

    def get_rows(
            self,
            table: str,
            search_column_name,
            search_value=None,
            lower_value=None,
            upper_value=None,
            exclusion_column_name=None,
            exclusion_value=None
    ):
        """
        Returns a list of Row objects where the specified value matches.
        Meant to be used within the class.

        Parameters:
                table (sqlalchemy.table): Table object
                column (sqlalchemy.column): Column object to search for value
                value (any): Value to search column for
                exclusion_column_name (sqlalchemy.column) Optional. Reject rows where this column equals exclusion_value
                exclusion_value (any) Optional. Required if exclusion_column is provided.

        Returns:
                result_rows: List of Row objects. Access rows in these ways: row.some_row, row['some_row']
        """
        the_table = self.tables[table]
        selection = select(the_table)
        search_column = the_table.c[search_column_name]

        if search_value:
            selection = selection.where(search_column == search_value)
        elif lower_value and upper_value:
            selection = selection.where(search_column > lower_value).where(search_column < upper_value)
        else:
            raise ValueError('If search_value is not provided, both lower_value and upper_value must be.')

        if exclusion_column_name:
            exclusion_column = the_table.c[exclusion_column_name]
            if not exclusion_value:
                raise ValueError('No exclusion value provided.')
            selection = selection.where(exclusion_column != exclusion_value)

        with self.engine.begin() as conn:
            result_rows = conn.execute(selection).all()

        if len(result_rows) == 0:
            if lower_value:
                raise ValueError(f'Could not find rows where "{search_column_name}" is between "{lower_value}" and "{upper_value}"')
            else:
                raise ValueError(f'Could not find rows where \"{search_column_name}\" is \"{search_value}\"')

        return result_rows


# Below is just for testing when this file is run from the command line
if __name__ == '__main__':
    db = HvzDb()
    result = db.get_rows('members', 'OZ', True)
    print(result)

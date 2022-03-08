from __future__ import annotations
import discord
import os.path
from dataclasses import dataclass, field, InitVar
from typing import List, Union, Dict, TYPE_CHECKING, Any, ClassVar
import copy

from sqlalchemy.engine.mock import MockConnection

if TYPE_CHECKING:
    from discord_hvz import HVZBot
from datetime import datetime

import sqlalchemy
from sqlalchemy import create_engine, MetaData
from sqlalchemy import text
from sqlalchemy import MetaData
from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy import insert, select, delete, update
from sqlalchemy import func, cast, and_
from sqlalchemy.exc import NoSuchTableError, CompileError

from config import config, ConfigError

from loguru import logger

log = logger

@dataclass
class HvzDb:
    engine: sqlalchemy.engine.Engine = field(init=False)
    metadata_obj: MetaData = field(init=False, default_factory=MetaData)
    tables: Dict[str, Table] = field(init=False, default_factory=dict)

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
        'boolean': Boolean,
        'datetime': DateTime
    }

    
    def __post_init__(self):
        database_config: Dict[str, Dict[str, str]] = copy.deepcopy(config['database_tables'])
        self.engine = create_engine("sqlite+pysqlite:///hvzdb.db", future=True)

        for table_name, column_dict in database_config.items():
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


        # Give each table a table_names tuple which is all column names
        for name, table in self.tables.items():
            selection = select(table)
            with self.engine.begin() as conn:
                result = conn.execute(selection)
                table.column_names = result.keys()

    def _create_column_object(self, column_name: str, column_type: str) -> Column:
        """
        Returns a Column object after forcing the name to lowercase and validating the type
        :param column_name:
        :param column_type: A string matching a valid column type
        :return: Column object
        """
        try:
            column_type = self.valid_column_types[column_type.casefold()]
        except KeyError:
            column_type = String

        return Column(column_name.casefold(), column_type)

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
            return result


    def get_member(self, value, column=None):
        """
        Returns a Row object that represents a single member in the database

        Parameters:
                member (int or user): A user id or a discord.abc.User object

        Returns:
                row (Row): Row object. Access rows in these ways: row.some_row, row['some_row']
        """
        if column is not None:
            search_value = value
            search_column = column
        else:
            search_column = 'ID'
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

    def get_table(self, table):
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
        result = self.__edit_row(
            self.tables['members'],
            self.tables['members'].c.ID,
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

        result = self.__edit_row(
            self.tables['tags'],
            self.tables['tags'].c.Tag_ID,
            tag_id,
            column,
            value
        )
        return result

    def __edit_row(self, table, search_column, search_value, target_column, target_value):
        updator = (
            update(table).where(search_column == search_value).
                values({target_column: target_value})
        )

        if target_column not in table.column_names:
            raise ValueError(f'{search_column} not a column in {table}')

        with self.engine.begin() as conn:
            result = conn.execute(updator)
        if result.rowcount > 0:
            return True
        else:
            raise ValueError(f'\"{search_value}\" not found in \"{search_column}\" column.')

    def delete_member(self, member):
        member_id = member
        if isinstance(member, discord.abc.User):
            member_id = member.id

        self.__delete_row(
            self.tables['members'],
            self.tables['members'].c.ID,
            member_id
        )
        return

    def delete_tag(self, tag_id):
        table = self.tables['tags']
        self.__delete_row(
            table,
            table.c.Tag_ID,
            tag_id
        )
        return

    def __delete_row(self, table, search_column, search_value):

        if search_column not in table.column_names:
            raise ValueError(f'{search_column} not a column in {table}')

        deletor = delete(table).where(search_column == search_value)
        with self.engine.begin() as conn:
            conn.execute(deletor)
            return True

    def get_rows(self, table, search_column, search_value, exclusion_column=None, exclusion_value=None):
        """
        Returns a list of Row objects where the specified value matches.
        Meant to be used within the class.

        Parameters:
                table (sqlalchemy.table): Table object
                column (sqlalchemy.column): Column object to search for value
                value (any): Value to search column for
                exclusion_column (sqlalchemy.column) Optional. Reject rows where this column equals exclusion_value
                exclusion_value (any) Optional. Required if exclusion_column is provided.

        Returns:
                result_rows: List of Row objects. Access rows in these ways: row.some_row, row['some_row']
        """
        the_table = self.tables[table]
        selection = select(the_table).where(the_table.c[search_column] == search_value)
        if exclusion_column is not None:
            if exclusion_value is None:
                raise ValueError('No exclusion value provided.')
            selection = selection.where(the_table.c[exclusion_column] != exclusion_value)
        with self.engine.begin() as conn:
            result_rows = conn.execute(selection).all()
        if len(result_rows) == 0:
            raise ValueError(f'Could not find rows where \"{search_column}\" is \"{search_value}\"')
        return result_rows


# Below is just for testing when this file is run from the command line
if __name__ == '__main__':
    db = HvzDb()
    result = db.get_rows('members', 'OZ', True)
    print(result)

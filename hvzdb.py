import discord
import logging
import os.path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import MetaData
from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import insert, select, delete, update
from sqlalchemy import func, cast
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy import and_

log = logging.getLogger(__name__)


class HvzDb():
    def __init__(self):
        self.metadata_obj = MetaData()
        self.engine = create_engine("sqlite+pysqlite:///hvzdb.db", future=True)
        
        self.tables = {'members': None, 'tags': None}
        for n in self.tables:

            try:
                self.tables[n] = Table(n, self.metadata_obj, autoload_with=self.engine)
            except NoSuchTableError:
                if n == 'members':
                    log.critical('There is no members table, so I\'m making it.')
                    self.tables[n] = Table(
                        'members',
                        self.metadata_obj,
                        Column('ID', String, primary_key=True, nullable=False),
                        Column('Name', String),
                        Column('Nickname', String),
                        Column('Discord_Name', String),
                        Column('CPO', String),
                        Column('Faction', String),
                        Column('Tag_Code', String),
                        Column('OZ_Desire', String),
                        Column('Email', String),
                        Column('Want_Bandana', String),
                        Column('Registration_Time', DateTime),
                        Column('OZ', Boolean)
                    )
                elif n == 'tags':
                    log.critical('There is no tags table, so I\'m making it.')
                    self.tables[n] = Table(
                        'tags',
                        self.metadata_obj,
                        Column('Tag_ID', Integer, primary_key=True, nullable=False, autoincrement=True),
                        Column('Tagger_ID', String),
                        Column('Tagger_Name', String),
                        Column('Tagger_Nickname', String),
                        Column('Tagger_Discord_Name', String),
                        Column('Tagged_ID', String),
                        Column('Tagged_Name', String),
                        Column('Tagged_Nickname', String),
                        Column('Tagged_Discord_Name', String),
                        Column('Tag_Time', DateTime),
                        Column('Report_Time', DateTime),
                        Column('Revoked_Tag', Boolean)
                    )
        
        self.metadata_obj.create_all(self.engine)


        # self.tag_logging_table = Table('tag_logging', self.metadata_obj, autoload_with=self.engine)

        # Give each table a keys tuple which is all column names
        for n, t in self.tables.items():
            selection = select(t)
            with self.engine.begin() as conn:
                result = conn.execute(selection)
                t.keys = result.keys()


    def add_member(self, member_row):
        '''
        Adds a member to the database

        Parameters:
                member_row (dict): A dict with pairs of column_name:value. Example:
                                    {'Name': 'George Soros', 'CPO': 9001, ...}

        Returns:
                result (result object?): This needs work.
        '''
        result = self.__add_row(self.tables['members'], member_row)
        return result

    def add_tag(self, tag_row):
        '''
        Adds a tag to the database

        Parameters:
                tag_row (dict): A dict with pairs of column_name:value. Example:
                                    {'Tag_ID': 'George Soros', 'CPO': 9001, ...}

        Returns:
                result (result object?): This needs work.
        '''
        result = self.__add_row(self.tables['tags'], tag_row)
        return result

    def __add_row(self, table, row):

        with self.engine.begin() as conn:
            result = conn.execute(insert(table), row)
            return result


    def get_member(self, value, column=None):
        '''
        Returns a Row object that represents a single member in the database

        Parameters:
                member (int or user): A user id or a discord.abc.User object

        Returns:
                row (Row): Row object. Access rows in these ways: row.some_row, row['some_row']
        '''
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
            if search_column not in table.keys:
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
        '''
        Returns a list of all members in the database

        Parameters:
                table (str): The name of the table to fetch. Lower case

        Returns:
                result (list[Row]): List of Rows. Rows are like tuples, but with dictionary
                                                keys. Like this: row['Name'] or row.Name
        '''
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
        '''
        Edits an attribute of a member in the database

        Parameters:
                member (int or user): A user id or a discord.abc.User object
                column (str): A string matching the column to change. Case sensitive.
                value (any?): Value to change the cell to.

        Returns:
                result (bool): True if the edit was successful, False if it was not.
        '''
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
        '''
        Edits an attribute of a tag in the database

        Parameters:
                tag_id (int or user): A tag ID
                column (str): A string matching the column to change. Case sensitive.
                value (any?): Value to change the cell to.

        Returns:
                result (bool): True if the edit was successful, False if it was not.
        '''

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

        if target_column not in table.keys:
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

        if search_column not in table.keys:
            raise ValueError(f'{search_column} not a column in {table}')

        deletor = delete(table).where(search_column == search_value)
        with self.engine.begin() as conn:
            conn.execute(deletor)
            return True

    def get_rows(self, table, search_column, search_value, exclusion_column=None, exclusion_value=None):
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
        the_table = self.tables[table]
        selection = select(the_table).where(the_table.c[search_column] == search_value)
        if (exclusion_column is not None):
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

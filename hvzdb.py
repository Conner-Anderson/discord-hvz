import discord
import logging
import os.path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import MetaData
from sqlalchemy import Table, Column, Integer, String, DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import insert, select
from sqlalchemy import update
from sqlalchemy import func, cast
from sqlalchemy.exc import NoSuchTableError

log = logging.getLogger(__name__)


class HvzDb():
    def __init__(self):
        new_file = False
        self.metadata_obj = MetaData()
        if not os.path.exists('hvzdb.db'):
            new_file = True

        self.engine = create_engine("sqlite+pysqlite:///hvzdb.db", future=True)

        if new_file is False:
            try:
                self.members_table = Table('members', self.metadata_obj, autoload_with=self.engine)
            except NoSuchTableError:
                log.error('No such table')
                new_file = True

        if new_file is True:
            self.members_table = Table(
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
                Column('Registration_Time', DateTime)
            )
            self.metadata_obj.create_all(self.engine)


        # self.tag_logging_table = Table('tag_logging', self.metadata_obj, autoload_with=self.engine)

        
        selection = select(self.members_table)
        with self.engine.begin() as conn:
            result = conn.execute(selection)
            self.members_table.keys = result.keys()


    def add_member(self, member_row):
        '''
        Adds a member to the database

        Parameters:
                member_row (dict): A dict with pairs of column_name:value. Example:
                                    {'Name': 'George Soros', 'CPO': 9001, ...}

        Returns:
                result (result object?): This needs work.
        '''
        result = self.__add_row(self.members_table, member_row)
        return result

    def __add_row(self, table, row):

        with self.engine.begin() as conn:
            result = conn.execute(insert(self.members_table), row)
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


        member_row = self.__get_row(self.members_table, self.members_table.c[search_column], search_value)
        return member_row


    def __get_row(self, table, column, value):
        '''
        Returns the first Row object where the specified value matches.
        Meant to be used within the class.

        Parameters:
                table (sqlalchemy.table): Table object
                column (sqlalchemy.column): Column object to search for value
                value (any): Value to search column for

        Returns:
                row (Row): Row object. Access rows in these ways: row.some_row, row['some_row']
        '''
        selection = select(table).where(column == value)
        with self.engine.begin() as conn:
            result_row = conn.execute(selection).first()
            return result_row


    def get_members(self):
        '''
        Returns a list of all members in the database

        Parameters:
                none

        Returns:
                members_result (list[Row]): List of Rows. Rows are like tuples, but with dictionary
                                                keys. Like this: row['Name'] or row.Name
        '''
        selection = select(self.members_table)
        with self.engine.begin() as conn:
            members_result = conn.execute(selection).all()
            return members_result

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
            self.members_table,
            self.members_table.c.ID,
            member_id,
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
            return False

        with self.engine.begin() as conn:
            conn.execute(updator)
            return True


# Below is just for testing when this file is run from the command line
if __name__ == '__main__':
    db = HvzDb()
    print(db.get_member('H9K9F-', 'Tag_Code').Name)
    print(db.edit_member(509173983132778506, 'Faction', 'human'))
    members = db.get_members()

    for m in members:
        msg = ''
        for x in m:
            msg += f'{x} '
        print(msg)

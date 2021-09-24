import sqlite3
from sqlite3 import Error
import discord
import logging

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import MetaData
from sqlalchemy import Table, Column, Integer, String
from sqlalchemy import ForeignKey
from sqlalchemy import insert, select
from sqlalchemy import update
from sqlalchemy import func, cast

log = logging.getLogger(__name__)

# TODO: convert this to use SQLAlchemy, an ORM

class HvzDb():
    def __init__(self):

        self.engine = create_engine("sqlite+pysqlite:///hvzdb.db", future=True)
        self.metadata_obj = MetaData()

        self.members_table = Table('members', self.metadata_obj, autoload_with=self.engine)
        self.tag_logging_table = Table('tag_logging', self.metadata_obj, autoload_with=self.engine)


        
        
        selection = select(self.members_table)
        with self.engine.begin() as conn:
            result = conn.execute(selection)
            self.members_table.keys = result.keys()



    def add_row(self, table, row):
        # Assembles an SQL statement to make a new row (tag, member, etc.)
        # Permits SQL injection attacks, but we can fix that later
        columns = ''
        values = ''
        for key in row:
            columns += ('\'' + key + '\',')
            values += ('\'' + row[key] + '\',')
        columns = columns[:-1]
        values = values[:-1]

        sql = f''' INSERT INTO {table}({columns})
                  VALUES({values})'''

        cur = self.conn.cursor()
        cur.execute(sql)
        self.conn.commit()
        return cur.lastrowid

    def delete_row(self, table, member):

        member_id = member
        if isinstance(member, discord.abc.User):
            member_id = member.id

        sql = f''' DELETE FROM {table}
                WHERE ID = {member_id};
        '''

        cur = self.conn.cursor()
        cur.execute(sql)
        self.conn.commit()
        return 1

    def get_table(self, table):
        cur = self.conn.cursor()
        rows = cur.execute(f'SELECT * FROM {table}').fetchall()
        columns = cur.description
        rows.insert(0, [c[0] for c in columns])
        return rows

    def get_member(self, member):
        '''
        Returns a Row object that represents a single member in the database

        Parameters:
                member (int or user): A user id or a discord.abc.User object

        Returns:
                row (Row): Row object. Access rows in these ways: row.some_row, row['some_row']
        '''
        member_id = member
        if isinstance(member, discord.abc.User):
            member_id = member.id

        member_row = self.__get_row(self.members_table, self.members_table.c.ID, member_id)
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

    def get_column(self, table:str, column:str):
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


    class DBError(Exception):
        pass

    def dump(self, obj):
        '''Prints the passed object in a very detailed form for debugging'''
        for attr in dir(obj):
            log.debug("obj.%s = %r" % (attr, getattr(obj, attr)))

if __name__ == '__main__':
    db = HvzDb()
    print(db.get_member(509173983132778506).Name)
    print(db.edit_member(509173983132778506, 'Faction', 'human'))

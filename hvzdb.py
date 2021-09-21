import sqlite3
from sqlite3 import Error
import discord

# TODO: convert this to use SQLAlchemy, an ORM

class HvzDb():
    def __init__(self):
        database = r"hvzdb.db"
        # Create databases. It would be nice to make this variable, but it is easier to code
        # everything else if this is easy to read.
        # There is some remnant code here from earlier tests
        sql_create_members_table = """ CREATE TABLE IF NOT EXISTS members (
                                            ID text PRIMARY KEY,
                                            Name text NOT NULL,
                                            CPO text,
                                            Faction text,
                                            Tag_Code text,
                                            OZ_Desire text,
                                            Email text,
                                            Want_Bandana text
                                        ); """

        sql_create_tasks_table = """CREATE TABLE IF NOT EXISTS tag_logging (
                                        Tag_Code text PRIMARY KEY,
                                        Tag_Day text,
                                        Tag_Time time,
                                        Log_Time time
                                    );"""
        self.conn = self.create_connection(database)
        # self.conn.row_factory = sqlite3.Row  # Queries of rows now return Row objects. They are similar to tuples, but with dict-like functions

        if self.conn is not None:

            self.create_table(self.conn, sql_create_members_table)
            self.create_table(self.conn, sql_create_tasks_table)
        else:
            print('Error! Cannot create this database connection!')


    def create_connection(self, db_file):
        """ create a database connection to a SQLite database """
        conn = None
        try:
            conn = sqlite3.connect(db_file)
        except Error as e:
            print(e)

        return conn

    def create_table(self, conn, create_table_sql):

        try:
            c = conn.cursor()
            c.execute(create_table_sql)
            self.conn.commit()
        except Error as e:
            print(e)

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
        print('get_table rows:', rows)
        columns = cur.description
        rows.insert(0, [c[0] for c in columns])
        return rows

    def get_member(self, member):
        # Returns a row<list> from the database. Takes a member object or id.
        output_row = {}
        member_id = member
        if isinstance(member, discord.abc.User):
            member_id = member.id

        sql = f'SELECT * FROM members WHERE ID = {member_id}'
        cur = self.conn.cursor()
        try:
            row = cur.execute(sql).fetchone()
            if row is not None:
                columns = cur.description
                for c, x in enumerate(row):
                    output_row[columns[c][0]] = x
        except sqlite3.OperationalError as e:
            raise ValueError(e)
        return output_row

    def get_row(self, table, column, value):
        # Returns the first row that matches. The row is a dict, where the keys are column names
        print(self, table, column, value)
        output = None
        sql = f'''SELECT * FROM {table}
                WHERE {column} = \'{value}\''''
        cur = self.conn.cursor()

        row = cur.execute(sql).fetchone()
        if row is not None:
            columns = cur.description
            output = {}
            for c, x in enumerate(row):
                output[columns[c][0]] = x

        return output

    def edit_member(self, member, column, value):
        try:
            member_id = member
            if isinstance(member, discord.abc.User):
                member_id = member.id

            sql = f'''UPDATE members
                    SET {column} = \'{value}\'
                    WHERE ID = \'{member_id}\'
            '''
            cur = self.conn.cursor()
            cur.execute(sql)
            self.conn.commit()
        except sqlite3.OperationalError as e:
            raise ValueError(e)


    def create_project(self, conn, project):
        # Leftover example code
        sql = ''' INSERT INTO projects(name,begin_date,end_date)
                  VALUES(?,?,?) '''
        cur = self.conn.cursor()
        cur.execute(sql, project)
        self.conn.commit()
        return cur.lastrowid

    class DBError(Exception):
        pass

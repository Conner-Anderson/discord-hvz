import sqlite3
from sqlite3 import Error

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
                                            Faction text
                                        ); """

        sql_create_tasks_table = """CREATE TABLE IF NOT EXISTS tag_logging (
                                        Tag_Code text PRIMARY KEY,
                                        Tag_Day text,
                                        Tag_Time time,
                                        Log_Time time
                                    );"""
        self.conn = self.create_connection(database)   

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

    def delete_row(self, table, user_id):

        sql = f''' DELETE FROM {table}
                WHERE ID = {user_id};
        '''

        cur = self.conn.cursor()
        cur.execute(sql)
        self.conn.commit()
        return 1

    def get_table(self, table):
        cur = self.conn.cursor()
        rows = cur.execute(f'SELECT * FROM {table}').fetchall()
        columns = cur.execute(f'PRAGMA table_info({table})').fetchall()
        rows.insert(0, [c[1] for c in columns])
        return rows

    def create_project(self, conn, project):
        # Leftover example code
        sql = ''' INSERT INTO projects(name,begin_date,end_date)
                  VALUES(?,?,?) '''
        cur = self.conn.cursor()
        cur.execute(sql, project)
        self.conn.commit()
        return cur.lastrowid


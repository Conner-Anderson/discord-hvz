from __future__ import print_function, annotations
from config import config
import utilities as util
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from datetime import datetime
from loguru import logger
import logging
import asyncio

from typing import Dict, List, Any, Union, TYPE_CHECKING
if TYPE_CHECKING:
    import sqlalchemy
    from hvzdb import HvzDb

log = logger

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# ID of Google Sheet: can be taken from the sheet address. Google account must have permission
SPREADSHEET_ID = config['sheet_ids'][config['active_server']]
SAMPLE_RANGE_NAME = 'Output!A2:B'


class SheetsInterface:

    def __init__(self, db: HvzDb):
        self.setup(db)
        self.waiting_tables: Dict[str, asyncio.Task] = {}

    def setup(self, db):

        self.db = db
        """Shows basic usage of the Sheets API.
        Prints values from a sample spreadsheet.
        """
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        service = build('sheets', 'v4', credentials=creds)

        # Call the Sheets API and save it for other functions globally
        self.spreadsheets = service.spreadsheets()

    def check_creds(self):
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            if creds.valid:
                return
        self.setup(self.db)


    def update_table(self, table_name: str):
        # TODO: Generalize this feature for use elsewhere, such as display
        tables_to_pop = []
        for table, task in self.waiting_tables.items():
            if task.done():
                tables_to_pop.append(table)
            elif table == table_name:
                task.cancel()
                tables_to_pop.append(table)
                break
        for t in tables_to_pop: self.waiting_tables.pop(t)

        # Set timer to _export table to sheet
        task = asyncio.create_task(util.do_after_wait(self._export, 4.0, table_name))
        self.waiting_tables[table_name] = task



    def _export(self, table_name: str):
        # TODO: It would be nice if this didn't have to deal directly with the database. Not a huge deal.

        self.check_creds()

        table: List[sqlalchemy.engine.Row] = self.db.get_table(table_name)

        column_order_raw: Dict[str, str] = config['database_tables'][table_name]
        column_order = []
        for key in column_order_raw:
            column_order.append(key.casefold())

        # Let's turn the list of Rows into a list of lists. Google wants that.

        values = []
        for y, row in enumerate(table):
            values.append([])
            for x, column in enumerate(column_order):
                cell = row[column]
                if isinstance(cell, datetime):
                    cell = cell.isoformat()

                values[y].append(cell)

        values.insert(0, column_order)
        sheet_name = config['sheet_names'][table_name]

        # Erases entire sheet below row 1!
        self.spreadsheets.values().clear(spreadsheetId=SPREADSHEET_ID, range=f'\'{sheet_name}\'!A1:L').execute()

        body = {'values': values}

        try:
            result = self.spreadsheets.values().update(spreadsheetId=SPREADSHEET_ID, range=f'\'{sheet_name}\'!A1:L',
                                                       valueInputOption='USER_ENTERED', body=body).execute()
        except Exception as e:
            log.exception('There was an exception with the Google API request! Here it is: %s' % e)
        else:
            log.debug('{0} cells updated.'.format(result.get('updatedCells')))

    # Returns a 2D list of data requested from the specified range in the specified sheet. Range must be given in A1 notation
    # Currently cannot specify which spreadsheet to pull from, but that'll depend on how this function is used
    # Returns 0 if the reading fails
    def read_sheet(self, sheet_name, range):
        try:
            result = self.spreadsheets.values().get(spreadsheetId=SPREADSHEET_ID,
                                                    range='\'%s\'!%s' % (sheet_name, range)).execute()
        except Exception as e:
            s = str(e).split('Details: ')
            log.error('Error when excecuting read_sheet() with arguments \"%s\" and \"%s\"  ----> %s' % (
            sheet_name, range, s[1]))
            return 0
        else:
            return result.get('values', 0)

    ''' Old method of updating nicknames. Might want it later
    def update_nicknames(table):
        id_pairs = (('Nickname', 'ID'), ('Tagger_Nickname', 'Tagger_ID'), ('Tagged_Nickname', 'Tagged_ID'))


        rows = DB.get_table(table)
        for r in rows:
            for pair in id_pairs:
                try:
                    ID = r[pair[1]]
                    member = BOT.guild.get_member(int(ID))
                    DB.edit_member(member, pair[0], member.nick)
                    log.debug(f'Updated {member.name} nickname.')
                except Exception:
                    pass
    '''

    # Formats a number as a bijective base N string. For converting to A1 notation. Might use later.
    def bijective(self, n, base):
        chars = ''
        while n != 0:
            chars = chr((n - 1) % base + 97) + chars
            n = (n - 1) / base
        return chars

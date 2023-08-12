from __future__ import print_function, annotations

import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, TYPE_CHECKING

import google.auth.exceptions
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from loguru import logger

from .utilities import pool_function
from .config import config

if TYPE_CHECKING:
    import sqlalchemy
    from database import HvzDb

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

SAMPLE_RANGE_NAME = 'Output!A2:B'

CREDENTIALS_PATH = config.path_root / 'credentials.json'
TOKEN_PATH = config.path_root / 'token.json'


class SheetsInterface:
    db: HvzDb
    sheet_id: str

    def __init__(self, db: HvzDb):
        self.setup(db)
        self.waiting_tables: Dict[str, asyncio.Task] = {}
        self.sheet_id = config.sheet_id

    def setup(self, db):

        self.db = db
        """Shows basic usage of the Sheets API.
        Prints values from a sample spreadsheet.
        """
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

        # If the creds need to be refreshed, try to.
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except google.auth.exceptions.RefreshError:
                creds = None
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            # If there are no creds, or they are not valid, log in.
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(TOKEN_PATH, 'w') as token:
                token.write(creds.to_json())

        try:
            service = build('sheets', 'v4', credentials=creds)
        except:
            DISCOVERY_SERVICE_URL = 'https://sheets.googleapis.com/$discovery/rest?version=v4'
            service = build('sheets', 'v4', credentials=creds, discoveryServiceUrl=DISCOVERY_SERVICE_URL)

        # Call the Sheets API and save it for other functions globally
        self.spreadsheets = service.spreadsheets()

    def check_creds(self):
        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            if creds.valid:
                return
        self.setup(self.db)

    def update_table(self, table_name: str):
        pool_function(
            function=self._export,
            wait_seconds=10.0,
            table_name=table_name
        )

    def _export(self, table_name: str):
        # TODO: It would be nice if this didn't have to deal directly with the database. Not a huge deal.

        self.check_creds()

        table: List[sqlalchemy.engine.Row] = self.db.get_table(table_name)
        database_columns = self.db.get_column_names(table_name)

        column_order: List[str] = []
        for key in config.database_tables[table_name]:
            column_order.append(key.casefold())

        # Add columns that are in the database, but don't have their order declared in the config to the end.
        for column in database_columns:
            if column not in column_order:
                column_order.append(column)

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
        sheet_name = config.sheet_names[table_name]

        # Build a string that represents the range to overwrite for Sheets. Example: 'Members'!A:L
        range = f"'{sheet_name}'"
        if len(values) == 0:
            column_count = len(column_order)
        else:
            column_count = len(values[0])
        range += f'!A:{get_column_letter(column_count)}'


        # Erases all columns up to the number of columns that could be written.
        self.spreadsheets.values().clear(spreadsheetId=self.sheet_id, range=range).execute()

        body = {'values': values}

        try:
            result = self.spreadsheets.values().update(spreadsheetId=self.sheet_id, range=range,
                                                       valueInputOption='USER_ENTERED', body=body).execute()
        except Exception as e:
            logger.exception('There was an exception with the Google API request! Here it is: %s' % e)
        else:
            logger.debug('{0} cells updated.'.format(result.get('updatedCells')))

    # Returns a 2D list of data requested from the specified range in the specified sheet. Range must be given in A1 notation
    # Currently cannot specify which spreadsheet to pull from, but that'll depend on how this function is used
    # Returns 0 if the reading fails
    def read_sheet(self, sheet_name, range):
        try:
            result = self.spreadsheets.values().get(spreadsheetId=self.sheet_id,
                                                    range='\'%s\'!%s' % (sheet_name, range)).execute()
        except Exception as e:
            s = str(e).split('Details: ')
            logger.error('Error when excecuting read_sheet() with arguments \"%s\" and \"%s\"  ----> %s' % (
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



def get_column_letter(col_idx: int):
    """Convert a column number into a column letter (3 -> 'C')

    Right shift the column col_idx by 26 to find column letters in reverse
    order.  These numbers are 1-based, and can be converted to ASCII
    ordinals by adding 64.

    """
    # these indices correspond to A -> ZZZ and include all allowed
    # columns
    if not 1 <= col_idx <= 18278:
        raise ValueError("Invalid column index {0}".format(col_idx))
    letters = []
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx, 26)
        # check for exact division and borrow if needed
        if remainder == 0:
            remainder = 26
            col_idx -= 1
        letters.append(chr(remainder+64))
    return ''.join(reversed(letters))



if __name__ == '__main__':
    #Test code
    response = get_column_letter(1)
    print(response)

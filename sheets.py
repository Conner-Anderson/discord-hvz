from __future__ import print_function
from config import config
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import logging
from datetime import datetime
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
log = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# ID of Google Sheet: can be taken from the sheet address. Google account must have permission
SPREADSHEET_ID = config['sheet_ids'][config['active_server']]
SAMPLE_RANGE_NAME = 'Output!A2:B'

def setup(db, bot):
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
    global SPREADSHEETS
    SPREADSHEETS = service.spreadsheets()
    global DB
    DB = db
    global BOT
    BOT = bot


def export_to_sheet(table_name):

    table = DB.get_table(table_name)

    sheet_settings = config['sheet_settings'][table_name]

    # Let's turn the list of Rows into a list of lists. Google wants that.
    
    values = []
    for y, row in enumerate(table):
        values.append([])
        for x, c in enumerate(sheet_settings['column_order']):
            if isinstance(row[x], datetime):
                values[y].append(row[c].isoformat())
            else:
                values[y].append(row[c])

    values.insert(0, sheet_settings['column_order'])
    sheet_name = sheet_settings['sheet_name']

    # Erases entire sheet below row 1!
    SPREADSHEETS.values().clear(spreadsheetId=SPREADSHEET_ID, range=f'\'{sheet_name}\'!A1:L').execute()

    body = {'values': values}

    try:
        result = SPREADSHEETS.values().update(spreadsheetId=SPREADSHEET_ID, range=f'\'{sheet_name}\'!A1:L', valueInputOption='USER_ENTERED', body=body).execute()
    except Exception as e:
        log.exception('There was an exception with the Google API request! Here it is: %s' % (e))
    else:
        log.debug('{0} cells updated.'.format(result.get('updatedCells')))

# Returns a 2D list of data requested from the specified range in the specified sheet. Range must be given in A1 notation
# Currently cannot specify which spreadsheet to pull from, but that'll depend on how this function is used
# Returns 0 if the reading fails
def read_sheet(sheet_name, range):
    try:
        result = SPREADSHEETS.values().get(spreadsheetId=SPREADSHEET_ID, range='\'%s\'!%s' % (sheet_name, range)).execute()
    except Exception as e:
        s = str(e).split('Details: ')
        log.error('Error when excecuting read_sheet() with arguments \"%s\" and \"%s\"  ----> %s' % (sheet_name, range, s[1]))
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
def bijective(n, base):
    chars = ''
    while n != 0:
        chars = chr((n - 1) % base + 97) + chars
        n = (n - 1) / base
    return chars


if __name__ == '__main__':
    setup()

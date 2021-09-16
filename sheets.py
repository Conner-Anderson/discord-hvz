from __future__ import print_function
from config import config
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import logging
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# ID of Google Sheet: can be taken from the sheet address. Google account must have permission
SPREADSHEET_ID = config['export_sheet_id']
SAMPLE_RANGE_NAME = 'Output!A2:B'

def setup(db):
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


def export_to_sheet(table_name):
    values = DB.get_table(table_name)

    # Temporary fix until we make the database system for variable
    sheet_names = {'registration': config['members_sheet_name'], 'tag_logging': config['tag_log_sheet_name']}
    # Erases entire sheet below row 1!
    SPREADSHEETS.values().clear(spreadsheetId=SPREADSHEET_ID, range=f'\'{sheet_names[table_name]}\'!A1:ZZZ').execute()

    body = {'values': values}

    try:
        result = SPREADSHEETS.values().update(spreadsheetId=SPREADSHEET_ID, range=f'\'{table_name}\'!A1:ZZZ', valueInputOption='USER_ENTERED', body=body).execute()
    except Exception as e:
        print('There was an exception with the Google API request! Here it is: %s' % (e))
    else:
        print('{0} cells updated.'.format(result.get('updatedCells')))

# Returns a 2D list of data requested from the specified range in the specified sheet. Range must be given in A1 notation
# Currently cannot specify which spreadsheet to pull from, but that'll depend on how this function is used
# Returns 0 if the reading fails
def read_sheet(sheet_name, range):
    try:
        result = SPREADSHEETS.values().get(spreadsheetId=SPREADSHEET_ID, range='\'%s\'!%s' % (sheet_name, range)).execute()
    except Exception as e:
        s = str(e).split('Details: ')
        print('Error when excecuting read_sheet() with arguments \"%s\" and \"%s\"  ----> %s' % (sheet_name, range, s[1]))
        return 0
    else:
        return result.get('values', 0)


# Formats a number as a bijective base N string. For converting to A1 notation. Might use later.
def bijective(n, base):
    chars = ''
    while n != 0:
        chars = chr((n - 1) % base + 97) + chars
        n = (n - 1) / base
    return chars


if __name__ == '__main__':
    setup()

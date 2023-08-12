from __future__ import annotations

import copy
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Union, Dict, TYPE_CHECKING, ClassVar

import discord
import sqlalchemy
from loguru import logger
from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean
from sqlalchemy import create_engine, MetaData
from sqlalchemy import select, delete, update
from sqlalchemy.engine import Row
from sqlalchemy.exc import NoSuchTableError

from discord_hvz.sheets import SheetsInterface
from discord_hvz.config import config

if TYPE_CHECKING:
    pass

def dump(obj):
    """Prints the passed object in a very detailed form for debugging"""
    for attr in dir(obj):
        try:
            print("obj.%s = %r" % (attr, getattr(obj, attr)))
        except Exception:
            print('TYPE ERROR')

@dataclass
class HvzDb:
    engine: sqlalchemy.engine.Engine = field(init=False)
    metadata_obj: MetaData = field(init=False, default_factory=MetaData)
    tables: Dict[str, Table] = field(init=False, default_factory=dict)
    sheet_interface: SheetsInterface = field(init=False, default=None)
    filepath: Path = config.database_path
    database_config: Dict[str, Dict[str, str]] = field(init=False, default_factory=dict)

    # Table names that cannot be created in the config. Reserved for cogs / modules
    reserved_table_names: ClassVar[List[str]] = ['persistent_panels']

    required_columns: ClassVar[Dict[str, Dict[str, str]]] = {
        'members': {
            'id': 'String',
            'name': 'String',
            'faction': 'String',
            'tag_code': 'String',
            'oz': 'Boolean'
        },
        'tags': {
            'tag_id': 'Integer',
            'tagger_id': 'String',
            'tagger_name': 'String'
        }
    }

    valid_column_types: ClassVar[Dict[str, type]] = {
        'string': String,
        'integer': Integer,
        'incrementing_integer': Integer,
        'boolean': Boolean,
        'datetime': DateTime
    }

    
    def __post_init__(self):
        # TODO: Need to make sure the required tables are always created. Might be config-depended now...
        self.database_config: Dict[str, Dict[str, str]] = copy.deepcopy(config.database_tables)
        self.engine = create_engine(f"sqlite+pysqlite:///{str(self.filepath)}", future=True)

        if not self.filepath.exists():
            logger.warning(
                f"No database found at the path specified by 'database_path' in {config.filepath.name}. It will be created at {self.filepath} \n"
                "Now creating the needed tables..."
            )

        for table_name, column_dict in self.database_config.items():
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

        if config.google_sheet_export == True:
            self.sheet_interface = SheetsInterface(self)

    def prepare_table(self, table_name: str, columns: Dict[str, Union[str, type]]) -> None:
        """
        Creates a new table in the database if there is none, and loads the table from the database if it exists already.
        """
        try:
            self.tables[table_name] = Table(table_name, self.metadata_obj, autoload_with=self.engine)
        except NoSuchTableError:
            logger.warning(
                f'Creating table "{table_name}" since it was not found in the database.')

            column_args = []
            # Create Columns from the config
            for column_name, column_type in columns.items():
                column_args.append(self._create_column_object(column_name, column_type))

            self.tables[table_name] = Table(table_name.casefold(), self.metadata_obj, *column_args)

        self.metadata_obj.create_all(self.engine)
        self.tables[table_name].column_names = columns.keys()

    def delete_table(self, table_name: str):
        self.tables[table_name].drop(bind=self.engine)
        logger.warning(f'Deleted table named {table_name}')

    def _validate_table_selection(self, table: str | Table) -> Table:
        if isinstance(table, str):
            try:
                return self.tables[table]
            except KeyError:
                raise KeyError(f'{table} is not a table.') from None
        elif isinstance(table, Table):
            return table
        else:
            raise KeyError(f'{table} is not recognized as a table.')

    def _validate_column_selection(self, table: Table, *args: str) -> Column | List[Column]:
        if len(args) == 0:
            raise ValueError('Must supply a column name to validate.')
        result: List[Column] = []
        for column in args:
            try:
                result.append(table.c[column])
            except KeyError:
                raise ValueError(f'{column} not a column in {table.name}')

        if len(result) == 1:
            return result[0]
        else:
            return result

    def _table_updated(self, table: Union[Table, str]) -> None:
        """
        To be called whenever a function changes a table. This lets the Google Sheet update.
        :param table:
        :return:
        """
        try:
            if isinstance(table, Table): table_name = table.name
            else: table_name = table
            if table_name in self.database_config: # Only send to Sheets if the table is in config.yml
                self.sheet_interface.update_table(table_name)
        except Exception as e:
            # Allow sheet failure to silently pass for the user.
            logger.exception(f'The database failed to update to the Google Sheet with this error: {e}')


    def _create_column_object(self, column_name: str, column_type: Union[str, type]) -> Column:
        """
        Returns a Column object after forcing the name to lowercase and validating the type
        :param column_name:
        :param column_type: A string matching a valid column type
        :return: Column object
        """
        if not isinstance(column_type, str):
            if column_type in self.valid_column_types.items():
                column_type_object = column_type
            else:
                raise TypeError(f'column_type is an invalid type: {type(column_type)}')
        else:
            try:
                column_type_object = self.valid_column_types[column_type.casefold()]
            except KeyError:
                column_type_object = String

        kwargs = {}
        if column_type == 'incrementing_integer':
            kwargs = {'primary_key': True, 'nullable':False, 'autoincrement':True}

        return Column(column_name.casefold(), column_type_object, **kwargs)

    def __add_row(self, table, row):
        # Old function acting as an alias
        return self.add_row(table, row)

    def get_column_names(self, table: str) -> List[str]:
        # Returns a list of column names in a table
        _table = self._validate_table_selection(table)
        output = []
        for c in _table.c:
            output.append(c.name)
        return output

    def add_row(self, table_selection:str, input_row: Dict) -> sqlalchemy.engine.CursorResult:
        table = self.tables[table_selection.casefold()]

        row = {}
        # Convert all column names to lowercase
        for k, i in input_row.items():
            row[k.casefold()] = i

        with self.engine.begin() as conn:
            result = conn.execute(table.insert().values(row))
            self._table_updated(table)
            return result

    def get_member(self, value: discord.abc.User | int, column: str = None) -> Row:
        """
        Returns a Row object that represents a single member in the database

        Parameters:
                member (int or user): A user id or a discord.abc.User object

        Returns:
                row (Row): Row object. Access rows in these ways: row.some_row, row['some_row']
        """
        if column is not None:
            search_value = value
            search_column = column.casefold()
        else:
            search_column = 'id'
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
        else:
            search_column = 'tag_id'

        if filter_revoked is False:
            tag_row = self.__get_row(table, table.c[search_column], value)
        else:
            tag_row = self.__get_row(table, table.c[search_column], value,
                                     exclusion_column=table.c['revoked_tag'], exclusion_value=True)
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

    def get_table(self, table) -> List[Row]:
        _table = self._validate_table_selection(table)
        selection = select(_table)
        with self.engine.begin() as conn:
            result = conn.execute(selection).all()
            return result

    def edit_row(self, table: Table | str, search_column: str, search_value, target_column: str, target_value):
        _table = self._validate_table_selection(table)
        _search_column, _target_column = self._validate_column_selection(_table, search_column, target_column)
        updator = (
            update(_table).where(_search_column == search_value).
                values({_target_column: target_value})
        )

        with self.engine.begin() as conn:
            result = conn.execute(updator)
        if result.rowcount > 0:
            self._table_updated(_table)
            return True
        else:
            raise ValueError(f'\"{search_value}\" not found in \"{search_column}\" column.')

    def delete_row(self, table: Union[Table, str], search_column: str, search_value):
        _table = self._validate_table_selection(table)
        _search_column = self._validate_column_selection(_table, search_column)

        deletor = delete(_table).where(_search_column == search_value)
        with self.engine.begin() as conn:
            result = conn.execute(deletor)
        if result.rowcount < 1:
            raise ValueError(f'Could not find rows where \"{search_column}\" is \"{search_value}\"')
        self._table_updated(table)
        return True

    def get_rows(
            self,
            table: str,
            search_column_name: str,
            search_value=None,
            lower_value=None,
            upper_value=None,
            exclusion_column_name: str =None,
            exclusion_value=None
    ) -> List[Row]:
        """
        Returns a list of Row objects where the specified value matches.
        Meant to be used within the class.

        Parameters:
                table (sqlalchemy.table): Table object
                column (sqlalchemy.column): Column object to search for value
                value (any): Value to search column for
                exclusion_column_name (sqlalchemy.column) Optional. Reject rows where this column equals exclusion_value
                exclusion_value (any) Optional. Required if exclusion_column_name is provided.

        Returns:
                result_rows: List of Row objects. Access rows in these ways: row.some_row, row['some_row']
        """
        _table = self._validate_table_selection(table)
        selection = select(_table)
        _search_column = self._validate_column_selection(_table, search_column_name)

        if search_value:
            selection = selection.where(_search_column == search_value)
        elif lower_value and upper_value:
            selection = selection.where(_search_column > lower_value).where(_search_column < upper_value)
        else:
            raise ValueError('If search_value is not provided, both lower_value and upper_value must be.')

        if exclusion_column_name:
            _exclusion_column = self._validate_column_selection(_table, exclusion_column_name)
            if not exclusion_value:
                raise ValueError('No exclusion value provided.')
            selection = selection.where(_exclusion_column != exclusion_value)

        with self.engine.begin() as conn:
            result_rows: List[Row] = conn.execute(selection).all()

        if len(result_rows) == 0:
            if lower_value:
                raise ValueError(f'Could not find rows where "{search_column_name}" is between "{lower_value}" and "{upper_value}"')
            else:
                raise ValueError(f'Could not find rows where \"{search_column_name}\" is \"{search_value}\"')

        return result_rows


# Below is just for testing when this file is run from the command line
if __name__ == '__main__':
    pass
import aiosqlite
import json
import asyncio

class CustomObject:
    def __init__(self, **kwargs):
        self.flatten(**kwargs)
    def flatten(self, **kwargs):
        for a, b in kwargs.items():
            setattr(self, a, b)

class DB:
    def __init__(self, *, name=None, loop=None,auto=False):
        self.db = None
        self.sql_db = None
        if name:
            self.db_name = name
            if not name.endswith(".db"):
                self.db_name = name+".db"
        else:
            self.db_name = "Database.db"
        self.loop = loop or asyncio.get_event_loop()
        self.tables = []
        if auto:
            self.loop.create_task(self.initialize())

    async def initialize(self):
        self.db = await aiosqlite.connect(self.db_name)
        self.sql_db = self.db
        await self.add_tables()

    async def add_tables(self):
        db = self.db
        cursor = await self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = await cursor.fetchall()
        await cursor.close()
        tbls = [t[0] for t in tables]
        self.tables = tbls
        return tbls



    async def create_table(self, *, name = None, primary_key = {},values = {}):
        query = "CREATE TABLE IF NOT EXISTS {table_name}({primary_key},{values})"
        primary_name = [e for e in primary_key.keys()][0]
        primary_type = [e for e in primary_key.values()][0]
        primary_data = f"{primary_name} {primary_type} NOT NULL PRIMARY KEY"
        rest = ", ".join([f"{a} {b}" for a, b in values.items()])
        query = query.format(table_name = name, primary_key = primary_data, values = rest)
        await self.db.execute(query)
        await self.db.commit()
        obj = Table(self, name)
        await obj.initialize()
        return obj

    async def get_table(self, name):
        await self.add_tables()
        if not name in self.tables:
            return None
        obj = Table(self, name)
        await obj.initialize()
        return obj

class Column:
    def __init__(self, index,name,_type,not_null,default_value,primary_key):
        self.index = index
        self.name = name
        self.type = _type
        self.not_null = True if not_null else False
        self.default_value = default_value
        self.primary_key = True if primary_key else False
class Table:
    def __init__(self, db, name, auto=False):
        self.data = db
        self.db = db
        self.name = name
        self.table_headers = []
        self.header_objects = []
        self.primary_key = None
        self.cached = False
        if auto:
            self.data.loop.create_task(self.initialize())

    async def initialize(self):
        db = self.data.db
        cur = await db.execute(f"PRAGMA table_info('{self.name}')")
        data = await cur.fetchall()
        self.table_headers = [x[1] for x in data]
        await cur.close()
        for i in data:
            index, name, _type, not_null, default_value, primary_key = i
            formed = Column(index,name,_type,not_null,default_value,primary_key)
            self.header_objects.append(formed)
            if formed.primary_key:
                self.primary_key = formed
        self.cached = True
        print(self.table_headers)

    async def add_entry(self, **values):
        """This is used to add an entry to the Table"""
        query = "INSERT OR IGNORE INTO {table_name} ({table_headers}) VALUES({entry_values})"

        headers = ", ".join([e for e in values.keys()])
        entry_val = ", ".join("?"*len(values.values()))
        attrs = [e for e in values.values()]

        query = query.format(table_name = self.name, table_headers=headers, entry_values=entry_val)

        await self.data.db.execute(query, attrs)
        await self.data.db.commit()

    async def get_entries(self, *args,convert = True, listed=False, as_dict=False):
        """Gets Entries from SQL Table
        VALID ARGUMENTS TO PASS:
        A =  B
        A >  B
        A >= B
        A <= B
        A <= B
        if convert is True, every data is compiled into a Records object and then passed."""
        consts = args
        condition = condition = " AND ".join(consts)
        if not consts:
            query = "SELECT * FROM {table_name}"
        else:
            query = "SELECT * FROM {table_name} WHERE {condition}"
        query = query.format(condition = condition, table_name=self.name)
        cur = await self.data.db.execute(query)
        data = await cur.fetchall()
        await cur.close()
        if not data:
            return []
        if (convert and listed) or (convert and as_dict):
            raise ArgumentError("Incorrect arguments passed. only one can be True between arguments (convert, listed, as_dict)")
        #Data contains all the info retrieved. Compile into dicts and also get the primary key data
        if listed:
            data = self.compile_as_list(data)
            return data
        if as_dict:
            data = self.compile_as_dict(data)
            return data
        data = self.compile_as_obj(data)
        return Records(data)

    async def get_all_entries(self, *, convert=True, as_dict = False,listed=False):
        query = "SELECT * FROM {table_name}"
        cur = await self.data.db.execute(query.format(table_name=self.name))
        data = await cur.fetchall()
        await cur.close()

        if (convert and listed) or (convert and as_dict):
            raise ArgumentError("Incorrect arguments passed. only one can be True between arguments (convert, listed, as_dict)")
        #Data contains all the info retrieved. Compile into dicts and also get the primary key data
        if listed:
            data = self.compile_as_list(data)
            return data
        if as_dict:
            data = self.compile_as_dict(data)
            return data
        data = self.compile_as_obj(data)
        return Records(data)

    async def get_entry(self, key, *, convert=True, as_dict=False):
        """Gets a Single Entry from the SQL Table.
        This is used to find an entry with the primary key.
        If multiple filters are to be passed. would be better off checking get_entries"""

        query = "SELECT * FROM {table_name} WHERE {primary_key} = ?"
        cur = await self.data.db.execute(query.format(table_name=self.name, primary_key=self.primary_key.name), [key])
        data = await cur.fetchone()
        print(data)
        if not data:
            return []
        if convert and as_dict:
            raise ArgumentError("Incorrect arguments passed. only one can be True between arguments (convert, as_dict)")
        converted = self.compile_as_list([data])
        if as_dict:
            return data
        obj = Record(**converted[0])
        return obj
    async def update_entry(self, key_value, **values):
        checked = {}
        for a, b in values.items():
            if a in self.table_headers:
                checked[a] = b
        query = """UPDATE {table_name}
        SET {rest}
        WHERE {primary_key} = ?"""
        query = query.format(table_name=self.name,rest=", ".join(["{} = ?".format(e) for e in checked.keys()]), primary_key = self.primary_key.name)
        attrs = [e for e in checked.values()] + [key_value]
        await self.data.db.execute(query, attrs)
        await self.data.db.commit()
    def compile_as_list(self, data):
        """This returns the data in this Manner:
        >>>[{Row1},{Row2},{Row3},...]"""

        fut = []
        for i in data:
            s = {}
            for j in range(len(self.table_headers)):
                s[self.table_headers[j]] = i[j]
            fut.append(s)
        return fut
    def compile_as_dict(self, data):
        """This returns the data in this Manner
        >>>{"PrimaryValue1":{Row1}, "PrimaryValue2":{Row2},...}
        For This to work, the Primary Key <MUST> be a STR or INT literal"""
        fut = {}
        index = self.primary_key.index
        for i in data:
            popped = i.pop(index)
            head = self.table_headers.copy()
            head.pop(index)
            s = {}
            for j in range(len(head)):
                s[j] = i[j]
            fut[popped] = s
        return fut

    def compile_as_obj(self, data):
        """This returns the data in this Manner
        >>>[Record0, Record1, Record2, Record3,...]
        Similar to returning listed but as actual objects for better usage"""
        data = self.compile_as_list(data)
        print(data)
        fut = []
        for i in data:
            obj = Record(**i)
            obj._primary_key = self.primary_key
            fut.append(obj)
        return fut


class Records:
    def __init__(self, data):
        self.data = data
        self.__start = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.__start >= len(self.data):
            self.__start = 0
            raise StopIteration
        else:
            self.__start += 1
            return self.data[self.__start-1]
    def __getitem__(self, key):
        return self.data[key]

    def filter(self, func):
        """Filters the data according to the function.
        Function must have a single attribute obj which represents a Record Object
        Example Usage:

        def pred(obj):
            if obj.grade == 'A':
                return True

        filtered = records.filter(pred)

        Alternatively a lambda can be passed:

        filtered = records.filter(lambda obj: obj.grade == 'A')


        Returns:
        Records Object containing the new filtered Objects
        """

        d = self.data
        f = []
        for i in d:
            if func(i):
                f.append(i)
        return Records(f)
class Record(CustomObject):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._primary_key = None
        self._args = args
        self._kwargs = kwargs




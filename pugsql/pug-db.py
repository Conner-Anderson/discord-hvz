import pugsql

filename = './hvzdb.db'

queries = pugsql.module('.')
#queries.connect('sqlite:///hvzdb.db')
queries.connect('sqlite:///hvzdb.db')



if __name__ == '__main__':
    print(queries)
    queries.get_member(table='tags', id=191386655620464640)
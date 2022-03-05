from dataclasses import dataclass, field, InitVar
from typing import Dict

@dataclass(frozen=True)
class Item:
    x: int
    stuff: Dict[str, str] = field(default_factory=dict)
    y: int = 1


    class Builder:
        def build(self):
            stuff = {'potato':'boil em', 'tater':'mash em'}
            keywords = {'x':99, 'stuff':stuff}
            return Item(**keywords)


item_builder = Item.Builder()
item1 = item_builder.build()

stuff = item1.stuff
stuff['potato'] = 'nasty'

print(item1.stuff)
print(stuff)


# a-mad-kings-quest
A text based adventure game

# Commands

### Doors

| Command | Description |
| ------- | ----------- |
| `go through door door_name` | Go through the door *door_name* |


### Rooms

| Command | Description |
| ------- | ----------- |
| `inspect room` | Provide information about the current room |

### Items

| Command | Description |
| ------- | ----------- |
| `open chest_name` | Attempt to unlock the chest *chest_name* |
| `pickup item_name` | Remove an item from the room and place it in the player's inventory |
| `drop item_name` | Remove an item from the player's inventory and place it in the room |
| `use item_name` | Use a food item for increased health |
| `equip item_name` | Equip a weapon or armor, unequipping any previously equipped item of the same type |
| `unequip item_name` | Unequip a weapon or armor |
| `inspect item_name` | Inspect any item in the player's inventory |

### Player

| Command | Description |
| ------- | ----------- |
| `access inventory` | Retrieve a list of all items in the player's inventory |
| `view equipment` | Retrieve a list of all currently equipped items |

### Gameplay

| Command | Description |
| ------- | ----------- |
| `help | help command` | Retrieve a list of currently available commands or help with a specific command |
| `save` | Save the current state of the game |
| `go back to last save` | Load the last save point for the current game |
| `restart` | Start the current game over from the beginning |
| `quit` | Exit back to the start menu without saving |

### Monsters

| Command | Description |
| ------- | ----------- |
| `attack` | Attack a monster in the current room |
| `inspect monster_name` | Retrieve information about a specific monster |
| `flee` | Retreat from the room back into the previous room |

### Puzzles

| Command | Description |
| ------- | ----------- |
| `solve guess` | Attempt to solve the current puzzle using *guess* |
| `hint` | Retrieve a hint about the current puzzle |
| `ignore` | Leave the puzzle unsolved |

### Start Menu

| Command | Description |
| ------- | ----------- |
| `create new game save_name` | Create a new game with the name *save_name* |
| `load save_name` | Load a previously saved game with the name *save_name* |
| `exit game` | Exit the program |

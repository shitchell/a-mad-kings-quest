# Coding

- [x] Create Entity class and all derived subclasses
- [x] Edit Game class to use EntityFactory to read config definitions and generate entities
- [ ] CommandController's
  - [ ] BaseCommandController *help, quit*
  - [ ] PuzzleCommandController *puzzle commands: solve, hint, ignore*
  - [ ] StartCommandController *start menu commands*
  - [ ] GameCommandController *in-game commands*
  - [ ] AttackCommandController *in-fight commands*
- [ ] Documentation
  - [ ] comments
  - [ ] command usage
- [ ] Commands
  - [ ] ensure all output matches SRS
  - [x] monster: flee
  - [x] monster: inspect
  - [ ] monster: bos003 win
- [ ] 50% chance of item not spawning in room on first entrance
- [ ] 20 item max for inventory

## Misc Coding

- [x] Map.teleport_player(Room room)
- [x] Map.get_rooms(Door door)
- [ ] Puzzle.activate()
- [x] Puzzle Door.puzzle
- [x] Key Door.key
- [x] Room.has_door(string eid)
- [x] Room.get_door(string eid)
- [x] Room.inspect()
- [x] Inventory.contains(string eid)

# Optional

- [ ] Allow infinitely nested items via recursion

# Config files

- [ ] map.json
  - [x] add examples
- [x] keys.json
  - [x] add examples
- [ ] puzzles.json
  - [ ] add examples
- [x] monsters.json
- [x] items.json

# Presentation

- [x] Everything

# Post-Presentation

- [ ] documentation
- [ ] line by line mvc
- [ ] structure of json
import os
import re
import sys
import uuid
import json
import time
import shlex
import string
import random
import hashlib
try:
	import readline
except:
	import pyreadline as readline
from inspect import getframeinfo, stack

# Exceptions
class InvalidSettingsFile(Exception): pass
class InvalidDirection(Exception): pass
class PlayerIsDead(Exception): pass
class MapNotFound(Exception): pass

# Debug level
# Higher level increases output
DEBUG = 0
_log_file = open("log.txt", "a")
def _log(*args, level=3):
	timestamp = time.strftime("[%Y-%m-%d_%H:%M:%S]")
	caller = stack()[1][0]
	caller_class = caller.f_locals["self"].__class__.__qualname__
	caller_lineno = getframeinfo(caller).lineno
	preface = "%s <%s:%i>" % (timestamp, caller_class, caller_lineno)
	if DEBUG >= level:
		print(preface + " ", *args)
	# Always print to log file
	print(preface + " ", *args, file=_log_file)
	_log_file.flush()

def _md5(text):
	return hashlib.md5(text.encode("utf-8")).hexdigest()

class CommandController:
	def __init__(self, game):
		self.game = game
		self._is_active = True
		self.enable_completion()

	# Method for tab completion
	def _completer(self, text, state):
		options = [x for x in self.get_command_names() if x.startswith(text)]
		if state < len(options):
			return options[state]
		else:
			return None

	def enable_completion(self):
		readline.parse_and_bind("tab: complete")
		readline.set_completer(self._completer)

	def is_active(self, value=None):
		if isinstance(value, bool):
			self._is_active = value
		return self._is_active

	def execute_line(self, line):
#		line_parts = shlex.split(line)
		line_parts = line.split(" ")
		if len(line_parts) > 0:
			_log("Executing line '%s'" % line, level=3)
			command = line_parts[0]
			args = line_parts[1:]
			func = self.get_command(command)
			if func:
				_log("running command '%s'" % command, level=4)
				try:
					output = func(*args)
				except Exception as e:
					output = str(e)
				_log("command output:", output, level=4)
				return output
			return "%s: command not found" % command

	def get_command(self, command):
		return self.get_commands().get(command.lower())

	def get_commands(self):
		commands = dict()
		command_names = filter(lambda x: x.startswith("do_"), dir(self))
		for command_name in command_names:
			func = getattr(self, command_name)
			if hasattr(func, "admin_command") and self.game.player.name != "admin":
				continue
			command_name = command_name[3:]
			commands[command_name] = func
		return commands

	def get_command_names(self):
		commands = self.get_commands()
		return list(commands.keys())

	def admin(func):
		def wrapper(self, *args, **kwargs):
			if self.game.player.name == "admin":
				return func(self, *args, **kwargs)
		wrapper.admin_command = True
		wrapper.__doc__ = func.__doc__
		return wrapper
	
	def do_help(self, *args, **kwargs):
		"""Prints help wth the game or a specific command"""
		if args:
			cmd = args[0]
			cmd = self.get_command(cmd)
			if cmd:
				return cmd.__doc__
			else:
				return "No such command!"
		else:
			return "Commands: " + ", ".join(self.get_command_names())

	def do_quit(self, *args, **kwargs):
		"""Exit the game"""
		sys.exit(1)

	@admin
	def do_admin(self, *args, **kwargs):
		"""Tells you if you're an admin"""
		return "YOU ARE ROOT"

	@admin
	def do_commands(self, *args, **kwargs):
		"""Return all commands and functions"""
		return self.get_commands()

	@admin
	def do_eval(self, *args):
		"""Execute a python statement"""
		if args:
			line = " ".join(args)
			try:
				if "=" in line:
					code = compile(line, "<string>", "exec")
				else:
					code = compile(line, "<string>", "eval")
				output = eval(code, {"game": self.game}, globals())
			except Exception as e:
				output = "Exception: " + str(e)
			return output

class GameCommandController(CommandController):
	def do_go(self, *args):
		"""Move through a door"""
		if len(args) == 3:
			if args[0] == "through" and args[1] == "door":
				door_id = args[2]
				# Get door from current room
				if self.game.map.current_room.has_door(door_id):
					# Door exists
					# If a monster is in the room, it attacks the player and prevents
					# them from leaving
					if self.game.map.current_room.monster:
						damage = self.game.map.current_room.monster.attack(self.game.player)
						output = "%s attacked" % self.game.map.current_room.monster.name
						if damage:
							output += " and did %i damage" % damage
						output += "!\n"
						output += "The monster stopped you from leaving\n"
						output += self.game.player.inspect()
						return output
					door = self.game.map.current_room.get_door(door_id)
					if door.key and not self.game.player.inventory.contains(eid=door.key.eid):
						return "Door requires key '%s'" % door.key
					elif door.puzzle and not door.puzzle.is_solved():
						# Activate puzzle
						self.game.view.output("A puzzle blocks the door...")
						# Print puzzle description
						self.game.view.output(door.puzzle.inspect())
						self.game.view.output()
						controller = PuzzleCommandController(self.game, door.puzzle)
						while controller.is_active():
							line = self.game.view.input()
							output = controller.execute_line(line)
							if output:
								self.game.view.output(output)
							if controller.is_active()
								self.game.view.output()
						del controller
						# Re-enable this controller's tab completion
						self.enable_completion()
						# If the puzzle still exists after activation, ignore the door
						if door.puzzle:
							return
					# If the key and puzzle requirements are satisfied, use the door
					rooms = self.game.map.get_rooms(door=door.eid)
					_log("Door '%s' matches" % door.eid, rooms, level=4)
					rooms.remove(self.game.map.current_room)
					if len(rooms) > 0:
						new_room = rooms[0]
						self.game.map.change_room(new_room.eid)
						return new_room.inspect()
					else:
						return "That door doesn't go anywhere!"
				else:
					return "No such door in current room"
		else:
			return "Invalid syntax!"

	def do_look(self, *args):
		"""Describe the current location"""
		return "You're in " + self.game.map.current_room.inspect()

	def do_inspect(self, *args):
		"""Inspect a monster in the current room"""
		if args:
			name = " ".join(args)
			# Collect all inspectable items
			items = dict()
			# Monster
			monster = self.game.map.current_room.monster
			if monster:
				items[monster.name] = monster
			_log("Inspectable items:", items, level=4)
			# Determine if name in items
			for key in items:
				if name.lower() in key.lower():
					return items[key].inspect()
			return "Could not find '%s'" % name
		return self.do_me()

	def do_inventory(self, *args):
		"""View items in player inventory"""
		if self.game.player.inventory:
			return ", ".join([item.name for item in self.game.player.inventory])
		else:
			return "No items in inventory!"

	def do_attack(self, *args):
		"""Try to attack the monster in the current room"""
		monster = self.game.map.current_room.monster
		player = self.game.player
		if monster:
			damage = player.attack(monster)
			output = "%s dealt %i damage!\n" % (player.name, damage)
			if not monster.is_alive():
				# Monster is dead
				self.game.map.current_room.remove_monster(monster.eid)
				output += "You defeated the monster!"
				# Get dropped items
				items = monster.get_dropped_items()
				if items:
					self.game.map.current_room.inventory.update(items)
					output += "\nSomething fell to the floor..."
			else:
				# Monster is alive and well
				# Attack player
				damage = monster.attack(player)
				# Add monster attack value
				output += "%s dealt %i damage!\n" % (monster.name, damage)
				if not player.is_alive():
					# Player is dead
					raise PlayerIsDead()
				output += "Player [%i]\tMonster [%i]" % (player.health, monster.health)
		else:
			output = "No monster in room!"
		return output

	def do_flee(self, *args):
		"""Make haste to the last room."""
		if self.game.map.change_room(history=1):
			return self.game.map.current_room.inspect()
		return "Nowhere to run!"

	### Sue me, sue me, everybody
	def do_me(self, *args):
	### Kick me, kick me, don't you black or white me
		"""Provide player info"""
		return self.game.player.inspect()

	## Admin commands
	@CommandController.admin
	def do_set_health(self, *args):
		"""Set player health to value"""
		if args:
			self.game.player.health = int(args[0])
		return self.do_me()

	@CommandController.admin
	def do_set_attack(self, *args):
		"""Set player attack to value"""
		if args:
			self.game.player._base_attack = int(args[0])
		return self.do_me()

	@CommandController.admin
	def do_rooms(self, *args):
		"""View list of all rooms"""
		rooms = [room.eid + ": " + room.name for room in self.game.map.get_rooms()]
		return "\n".join(rooms)

	@CommandController.admin
	def do_room(self, *args):
		"""Remotely inspect any room by ID"""
		rooms = list()
		for arg in args:
			room = self.game.map.get_room(arg, arg)
			if room:
				description = "%s: %s\n%s" % (
					room.eid,
					room.name,
					room.inspect()
				)
				rooms.append(description)
		return "\n\n".join(rooms)

	@CommandController.admin
	def do_debug(self, *args):
		"""Sets or displays debug level. Higher level increases output"""
		global DEBUG
		if args:
			try:
				DEBUG = int(args[0])
			except:
				return "Invalid debug level '%s'" % args[0]
		return "debug => " + str(DEBUG)

	@CommandController.admin
	def do_items(self, *args):
		"""Return a list of items on the map and their locations"""
		room_items = list()
		for room in self.game.map.get_rooms():
			for item in room.inventory.get_items():
				room_items.append("[%s] %s: %s" % (room.eid, room.name, item.name))
				for subitem in item.inventory.get_items():
					room_items.append("[%s] %s: %s => %s" % (room.eid, room.name, item.name, subitem.name))
		return "\n".join(room_items)

	@CommandController.admin
	def do_give(self, *args):
		"""usage: give item_1 item_2...\nAdd items to your inventory"""
		output = "Added"
		items_added = False
		for eid in args:
			entity = self.game.entity_factory.create_entity(eid)
			if isinstance(entity, Item):
				self.game.player.inventory.add(entity)
				output += " '%s'" % entity.name
				items_added = True
		if items_added:
			return output + "\n" + self.do_me()
		else:
			return "No valid item ids provided"

	@CommandController.admin
	def do_monsters(self, *args):
		"""Return a list of monsters on the map and their locations"""
		room_monsters = list()
		for room in self.game.map.get_rooms():
			for monster in room.get_monsters():
				room_monsters.append("[%s] %s: %s" % (room.eid, room.name, monster.name))
		return "\n".join(room_monsters)

class PuzzleCommandController(CommandController):
	def __init__(self, game, puzzle):
		super().__init__(game)
		self.puzzle = puzzle

	def do_solve(self, *args):
		"""usage: solve answer\nAttempt to solve the puzzle"""
		answer = " ".join(args)
		if self.puzzle.solve(answer):
			self.is_active(False)
			return "Correct! The puzzle is deactivated."
		return "Incorrect"

	def do_hint(self, *args):
		"""usage: hint\nReceive a hint for the puzzle"""
		return self.puzzle.get_hint()

	def do_ignore(self, *args):
		"""usage: ignore\nIgnore the puzzle and leave it unsolved"""
		self.is_active(False)

	def do_inspect(self, *args):
		"""usage: inspect\nView the puzzle description"""
		return self.puzzle.inspect()

	@CommandController.admin
	def do_solution(self, *args):
		"""Provide the puzzle solution"""
		solutions = list()
		for x in range(len(self.puzzle._solutions)):
		    solutions.append("%i: %s" % (x + 1, self.puzzle._solutions[x]))
		return "\n".join(solutions)

class Entity:
	def __init__(self, uid=None, eid=None, name="", description=""):
		self.uid = uid or uuid.uuid4().hex
		self.eid = eid
		self.name = name
		self.description = description

	def inspect(self):
		return "%s: %s" % (self.name, self.description)

	def __repr__(self):
		return "<%s [%s]>" % (self.__class__.__qualname__, self.eid)

class Item(Entity):
	def __init__(self, uid=None, eid=None, name="", description="", drop_chance=None):
		super().__init__(uid, eid, name, description)
		# All items can potentially contain other items
		self.inventory = Inventory()
		self._equippable = False
		self._usable = False
		try:
			self.drop_chance = float(drop_chance)
		except:
			self.drop_chance = 1

	def can_equip(self):
		return self._equippable

	def is_equipped(self, player):
		return self in player.equipped

	def can_use(self):
		return self._usable

class Key(Item): pass

class Equippable(Item):
	def __init__(self, uid=None, eid=None, name="", description="", drop_chance=None):
		# All items can potentially contain other items
		super().__init__(uid, eid, name, description, drop_chance)
		self._equippable = True

	def equip(self, player):
		# You can only have one of each combatitem type equipped,
		# so unequip any equipped items that share this class
		for item in player.equipped:
			if isinstance(item, self.__class__):
				item.unequip(player)
		player.equipped.append(self)

	def unequip(self, player):
		if self in player.equipped:
			player.equipped.remove(self)

class Usable(Item):
	def __init__(self, uid=None, eid=None, name="", description="", drop_chance=None):
		# All items can potentially contain other items
		super().__init__(uid, eid, name, description, drop_chance)
		self._usable = True

	def _on_use(self, player, inventory):
		pass
	
	# After using the item, it must be deleted from the inventory
	# By allowing the option to pass in an inventory, we allow the
	# option for a player to use their item on another player.
	# If no inventory is provided, the inventory in which the
	# item exists is assumed to be the player's own inventory
	def use(self, player, inventory=None):
		if not inventory:
			inventory = player.inventory
		
		# Ensure the item exists in the inventory
		if self in inventory:
			# Call the _on_use method. Inheriting classes
			# should overwrite _on_use() rather than use()
			self._on_use(player, inventory)
			# Remove the food item from the inventory
			inventory.remove(self)

class CombatItem(Equippable):
	def __init__(self, uid=None, eid=None, name="", description="", drop_chance=None, damage=0):
		super().__init__(uid, eid, name, description, drop_chance)
		self._damage = damage
		self._equipable = True

	@property
	def damage(self):
		return self._damage

	# Ensure that damage is always an integer
	@damage.setter
	def damage(self, value):
		try:
			self._damage = int(value)
		except:
			# If damage isn't already defined, set it to 0, else leave it unchanged
			if not hasattr(self, "_damage"):
				self._damage = 0

class Weapon(CombatItem): pass

class Armor(CombatItem): pass

class Food(Usable):
	def __init__(self, uid=None, eid=None, name="", description="", drop_chance=None, health=0):
		super().__init__(uid, eid, name, description, drop_chance)
		self._health = health

	@property
	def health(self):
		return self._health

	@health.setter
	def health(self, value):
		try:
			self._health = int(value)
		except:
			# If health isn't already defined, set it to 0, else leave it unchanged
			if not hasattr(self, "_health"):
				self._health = 0

	def _on_use(self, player, inventory=None):
		player.health += self.health

class Puzzle(Item):
	def __init__(self, uid=None, eid=None, name="", description="", solutions=list(), hints=list(), attempts=None):
		super().__init__(uid, eid, name, description)
		self._solutions = list()
		for solution in solutions:
			self.add_solution(solution)
		self._hints = list()
		for hint in hints:
			self.add_hint(hint)
		self._hint_index = 0
		try:
			self._attempts = int(attempts)
		except:
			self._attempts = None
		self._usable = True
		self._is_solved = False

	def _sanitize_solution(self, solution):
		# Lowercase
		solution = solution.lower()
		# Remove punctuation
		solution = solution.translate(str.maketrans('', '', string.punctuation))
		# Remove trailing / leading whitespace
		solution = solution.strip()
		return solution

	def add_solution(self, solution):
		solution = str(solution)
		self._solutions.append(solution)

	def add_hint(self, hint):
		hint = str(hint)
		if hint not in self._hints:
			self._hints.append(hint)

	# Rotate through all available hints and return
	# the next available hint with each call
	def get_hint(self):
		hints_len = len(self._hints)
		if hints_len > 0:
			hint_index = self._hint_index % hints_len
			self._hint_index += 1
			return self._hints[hint_index]

	def solve(self, guess):
		# Sanitize the guess
		guess = self._sanitize_solution(guess)
		for solution in self._solutions:
			solution = self._sanitize_solution(solution)
			_log("Comparing guess '%s' to answer '%s'" % (guess, solution), level=4)
			if solution == guess:
				self.is_solved(True)
				return True
		# Incorrect guess
		try:
			self._attempts -= 1
			if self._attempts < 0:
				self._attempts = 0
		except:
			pass
		return False

	def is_solved(self, value=None):
		if isinstance(value, bool):
			self._is_solved = value
		return self._is_solved

	def inspect(self):
		return self.description

class Inventory:
	def __init__(self, items=list()):
		self._items = list()
		# Ensure that only Entity objects are added
		try:
			for item in items:
				self.add(item)
		except:
			pass

	# Retrieve an item by entity id, unique id, or name
	# If name is given, match the closest named item
	def get(self, eid=None, uid=None, name=None):
		if name:
			name = str(name).lower()
		
		for item in self._items:
			if uid and uid == item.uid:
				return item
			elif eid and eid == item.eid:
				return item
			elif name and name in item.name.lower():
				return item

	# Retrieve an item that matches the object
	# and remove it from the inventory list
	def pop(self, eid=None, uid=None, name=None):
		item = self.get(eid, uid, name)
		if item:
			self._items.remove(item)
			return item

	def contains(self, eid=None, uid=None, name=None):
		return bool(self.get(eid, uid, name))

	# Add an item to the inventory list
	def add(self, item):
		if isinstance(item, Entity):
			self._items.append(item)

	# Add a list of items
	def update(self, items):
		try:
			for item in items:
				self.add(item)
		except:
			pass
	
	def get_items(self):
		return self._items

	def size(self):
		return len(self._items)

class Character(Entity):
	def __init__(self,
		uid = None,
		eid = None,
		name = "",
		description = "",
		health = 100,
		attack = 10,
		resistance = 0,
		armor = None,
		weapon = None,
		inventory = list()
	):
		self._name = None
		self.name = name
		super().__init__(uid, eid, name, description)

		# Stats
		self.health = health
		self._base_attack = attack
		self._base_resistance = resistance
		
		# Create an inventory and add any provided items
		self.inventory = Inventory()
		self.inventory.update(inventory)
		_log("Added %s to '%s' inventory" % (inventory, self.eid), level=5)
		_log("'%s' inventory" % self.eid, self.inventory.get_items(), level=5)

		# Equipable items
		self.equipped = list()
		self.equip(armor)
		self.equip(weapon)

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, value):
		if not value:
			value = "Character%i" % random.randrange(1111, 9999)
		else:
			value = str(value)
		_log("Changed player '%s' name to '%s'" % (self.name, value))
		self._name = value
	
	@property
	def health(self):
		return self._health
	
	@health.setter
	def health(self, value):
		try:
			self._health = int(value)
		except:
			return	
		if self._health < 0:
			self._health = 0
		if self._health == 0:
			_log("Character '%s' is dead" % self.name, level=2)
		else:
			_log("Set '%s' health to '%i'" % (self.name, self.health), level=2)

	## Combat
	def attack(self, character):
		damage = self.get_attack_damage()
		character.damage(damage)
		return damage

	def get_attack_damage(self):
		damage = self._base_attack
		if self.has_weapon():
			damage += self.get_weapon().damage
		return damage

	def damage(self, value):
		try:
			value = int(value)
		except:
			_log("invalid damage '%s'" % value)
		else:
			if self.has_armor():
				value -= self.get_armor().damage * value
			self.health -= value
		return self.health

	def is_alive(self):
		return self.health > 0
    
	## Armor
	def has_armor(self):
		return bool(self.get_armor())

	def get_armor(self):
		for item in self.equipped:
			if isinstance(item, Armor):
				return item

	## Weapon
	def has_weapon(self):
		return bool(self.get_weapon())

	def get_weapon(self):
		for item in self.equipped:
			if isinstance(item, Weapon):
				return item

	## Equip items
	def equip(self, item):
		if isinstance(item, Equippable):
			item.equip(self)
			# Ensure item is in inventory
			if item not in self.inventory.get_items():
				self.inventory.add(item)

	def unequip(self, item):
		if isinstance(item, Equippable):
			item.unequip(self)

	## Use items
	def use(self, item):
		if isinstance(item, Usable):
			item.use(self)

	## Get dropped items based on probability
	def get_dropped_items(self):
		items = list()
		for item in self.inventory.get_items():
			if random.random() <= item.drop_chance:
				items.append(item)
		return items

	## Custom inspect command
	def inspect(self):
		description = "%s | %i 🗡️ | %i ❤" % (
			self.name,
			self.get_attack_damage(),
			self.health
		)
		if self.description:
			description += "\n" + self.description
		if self.inventory.size() > 0:
			for item in self.inventory.get_items():
				description += "\n- " + item.name
				if item.is_equipped(self):
					description += " [equipped]"
		return description

class Player(Character): pass

class Monster(Character):
	def __init__(self,
		uid = None,
		eid = None,
		name = "",
		description = "",
		health = 100,
		attack = 10,
		resistance = 0,
		armor = None,
		weapon = None,
		inventory = list(),
		is_boss = False
	):
		super().__init__(uid, eid, name, description, health, attack, resistance, armor, weapon, inventory)
		self._is_boss = is_boss

	def is_boss(self):
		return bool(self._is_boss)

class Door(Entity):
	def __init__(self, uid=None, eid=None, puzzle=None, key=None):
		super().__init__(uid, eid, name=None, description=None)
		self.add_puzzle(puzzle)
		self.add_key(key)

	## Puzzle
	def add_puzzle(self, puzzle):
		self.puzzle = puzzle

	def has_puzzle(self):
		return isinstance(self.puzzle, Puzzle)

	## Key
	def add_key(self, key):
		self.key = key

	def has_key(self):
		return isinstance(self.key, Key)

class Room(Entity):
	def __init__(self, uid=None, eid=None, name="", description="", doors=list(), items=list(), monsters=None):
		super().__init__(uid, eid, name, description)
		# Add doors
		self.doors = list()
		try:
			for door in doors:
				self.add_door(door)
		except:
			pass

		# Add items to room
		self.inventory = Inventory()
		try:
			self.inventory.update(items)
		except:
			pass

		# Add monsters
		self._monsters = list()
		try:
			for monster in monsters:
				self.add_monster(monster)
		except:
			pass
		# Monster should be updated each time the room is entered
		self.monster = None

		# Default to not visited
		self._visited = False

	## Doors
	def add_door(self, door):
		if isinstance(door, Door):
			self.doors.append(door)

	def get_door(self, eid):
		for door in self.doors:
			if door.eid == eid:
				return door

	def has_door(self, eid):
		return bool(self.get_door(eid))

	def get_doors(self):
		return self.doors

	## Monsters
	def add_monster(self, monster):
		if isinstance(monster, Monster):
			self._monsters.append(monster)

	def remove_monster(self, eid=None, name=None):
		name = str(name).lower()
		# Remove monster from monster list
		for monster in self._monsters:
			if monster.eid == eid:
				self._monsters.remove(monster)
			elif name in monster.name.lower():
				self._monsters.remove(monster)
		# Remove room monster if match
		if self.monster:
			if self.monster.eid == eid:
				self.monster = None
			elif name in self.monster.name:
				self.monster = None

	def get_monster(self):
		# If a boss monster exists, return the boss monster
		for monster in self._monsters:
			if monster.is_boss():
				return monster
		# Else, return a random normal monster or no monster
		return random.choice(self._monsters + [None])

	def get_monsters(self):
		return self._monsters

	def enter(self):
		self.monster = self.get_monster()

	## Inspect
	def inspect(self):
		description = self.description
		if self.inventory.size() > 0:
			description += "\nItems:"
			for item in self.inventory.get_items():
				description += "\n - " + item.name
		if self.doors:
			description += "\nDoors:"
			for door in self.doors:
				description += "\n - " + door.eid
		if self.monster:
			description += "\nMonster:"
			description += "\n - " + self.monster.name
		if self._visited:
			description += "\nYou've been here before."
		return description

class EntityFactory:
	def __init__(self, entities=list()):
		self._entities = dict()
		if isinstance(entities, list):
			for entity in entities:
				self.add_entity(entity)

	# Add an entity definition / dict
	def add_definition(self, entity_dict):
		# Entity must be a dict...
		if isinstance(entity_dict, dict):
			# ...and have at least an id
			if entity_dict.get("id"):
				self._entities[entity_dict.get("id")] = entity_dict
				_log("Loaded entity definition '%s'" % entity_dict.get("id"), level=4)

	# Return an entity object based on an entity id
	def create_entity(self, eid):
		_log("Creating entity '%s'" % eid, level=4)
		if eid:
			if isinstance(eid, dict):
				custom_dict = eid
				eid = eid.get("id")
			else:
				custom_dict = dict()
				eid = str(eid)
			entity_dict = self._entities.get(eid)
			if entity_dict:
				entity_dict.update(custom_dict)
				generator = self._get_entity_generator(eid)
				if generator:
					return generator(entity_dict)
				else:
					_log("Generator not found for '%s'" % eid, level=4)
			else:
				_log("No entity definition found for '%s'" % eid, level=4)

	def create_entities(self, eids):
		_log("Creating entity list:", eids, level=4)
		entities = list()
		if isinstance(eids, list):
			for eid in eids:
				entity = self.create_entity(eid)
				entities.append(entity)
		return entities

	def _get_entity_generator(self, eid):
		entity_type = str(eid)[:3]
		generator_name = "_create_" + entity_type
		if hasattr(self, generator_name):
			generator = getattr(self, generator_name)
			return generator

	# Create an armor object
	def _create_arm(self, entity_dict):
		# eid, name, description, damage
		return Armor(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			damage = entity_dict.get("equip", dict()).get("armor"),
			drop_chance = entity_dict.get("probability")
		)

	# Create a boss monster object
	def _create_bos(self, entity_dict):
		entity_dict["is_boss"] = True
		return self._create_mon(entity_dict)

	# Create a chest object
	def _create_cst(self, entity_dict):
		chest = Item(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
		)
		# Add any contained items
		items = self.create_entities(entity_dict.get("items"))
		chest.inventory.update(items)
		return chest

	# Create a door object
	def _create_dor(self, entity_dict):
		# eid, puzzle, key
		# Create a puzzle if the door has a puzzle
		puzzle = self.create_entity(entity_dict.get("puzzle"))
		# Create a key if the door has a key
		key = self.create_entity(entity_dict.get("key"))
		return Door(
			eid = entity_dict.get("id"),
			puzzle = puzzle,
			key = key
		)
	
	# Create a food object
	def _create_fod(self, entity_dict):
		# eid, name, description, health
		return Food(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			health = entity_dict.get("health"),
			drop_chance = entity_dict.get("probability")
		)

	# Create a key object
	def _create_key(self, entity_dict):
		# eid, name, description
		return Key(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			drop_chance = entity_dict.get("probability")
		)

	# Create a monster object
	def _create_mon(self, entity_dict):
		# eid, name, description, health, attack, resistance, armor, weapon, inventory
		# Create any items in the inventory
		items = self.create_entities(entity_dict.get("items"))
		# Grab the weapon and armor from items
		armor = None
		weapon = None
		for item in items:
			if isinstance(item, Armor):
				armor = item
			elif isinstance(item, Weapon):
				weapon = item
		return Monster(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			health = entity_dict.get("health"),
			attack = entity_dict.get("attack"),
			resistance = entity_dict.get("armor"),
			armor = armor,
			weapon = weapon,
			inventory = items,
			is_boss = entity_dict.get("is_boss")
		)

	# Create a puzzle object
	def _create_puz(self, entity_dict):
		# eid, name, description, solutions, hints, attempts
		return Puzzle(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			solutions = entity_dict.get("solutions"),
			hints = entity_dict.get("hints")
		)

	# Create a room object
	def _create_rom(self, entity_dict):
		# eid, name, description, doors, items, monster
		# Create any doors
		doors = self.create_entities(entity_dict.get("doors"))
		_log("Created doors for room '%s':" % entity_dict.get("id"), doors, level=4)
		# Create any items
		items = self.create_entities(entity_dict.get("items"))
		# Create any monsters
		monsters = self.create_entities(entity_dict.get("monsters"))
		return Room(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			doors = doors,
			items = items,
			monsters = monsters
		)

	# Create a weapon object
	def _create_wep(self, entity_dict):
		# eid, name, description, damage
		return Weapon(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			damage = entity_dict.get("equip", dict()).get("attack"),
			drop_chance = entity_dict.get("probability")
		)

class Map:
	def __init__(self, rooms=list()):
		self._rooms = list()
		self._room_history = list()
		for room in rooms:
			self._add_room(room)

	## Rooms
	@property
	def current_room(self):
		if self._room_history:
			return self._room_history[-1]

	def add_room(self, room):
		if isinstance(room, Room):
			self._rooms.append(room)

	def get_random_room(self):
		return random.choice(self._rooms)

	def get_room(self, eid=None, name=None):
		if name:
			name = str(name).lower()
		for room in self._rooms:
			if room.eid == eid:
				return room
			elif name and name in room.name.lower():
				return room

	def get_rooms(self, name=None, door=None):
		if not name and not door:
			return self._rooms

		rooms = list()
		if name:
			name = str(name).lower()
		for room in self._rooms:
			if name and name in room.name.lower():
				rooms.append(room)
			elif door and room.has_door(door):
				rooms.append(room)
		return rooms

	def change_room(self, eid=None, name=None, history=None):
		try:
			history = int(history)
		except:
			history = None
		if history:
			# If the _room_history has only one entry, don't go back
			_room_history_len = len(self._room_history)
			if _room_history_len == 1:
				return False
			# Ensure history is no more than _room_history size - 1
			history_max = _room_history_len - 1
			history = history_max if history > history_max else history
			# Set the current room to visited
			self.current_room.visited = True
			# Slice the room history
			self._room_history = self._room_history[:-history]
			self.current_room.enter()
			return True
		elif not eid and not name:
			room = self.get_random_room()
		else:
			room = self.get_room(eid, name)
		if room:
			if isinstance(self.current_room, Room):
				self.current_room.visited = True
			self._room_history.append(room)
			room.enter()
			return True
		return False

class Game:
	"""TODO: Add doc"""
	# pylint: disable=too-many-instance-attributes
	def __init__(self, settings_filepath="config.json"):
		# Default attributes
		self._filepaths = {
			"config": None,
			"map": None,
			"entities": list()
		}
		self._is_running = True
		self.cmd_controller = None
		self.view = None
		self.characters = list()
		self._map = None
		map_entity_ids = list()

		# Load settings
		self._filepaths["config"] = settings_filepath
		self.settings = self.read_settings(settings_filepath)
		_log("Config:", self.settings, level=4)

		# Load entity definitions
		self.entity_factory = EntityFactory()
		for node in os.walk("entities"):
			directory = node[0]
			filepaths = node[2]
			for filepath in filepaths:
				filepath = os.path.join(directory, filepath)
				settings = self.read_settings(filepath)
				if settings:
					self._filepaths["entities"].append(filepath)
					for entity_dict in settings.get("entities"):
						self.entity_factory.add_definition(entity_dict)

		# Load map definitions
		map_filename = self.settings.get("map")
		if map_filename:
			map_filepath = os.path.join("maps", self.settings.get("map"))
			if not os.path.isfile(map_filepath):
				raise MapNotFound()
			settings = self.read_settings(map_filepath)
			if settings:
				self._filepaths["map"] = map_filepath
				for entity_dict in settings.get("entities"):
					self.entity_factory.add_definition(entity_dict)
					map_entity_ids.append(entity_dict.get("id"))
			else:
				raise MapNotFound()
		else:
			raise MapNotFound()

		# Create characters
		self.player = Player()
		self.characters.append(self.player)

		# Build game map
		self.build_map(map_entity_ids)

	def create_controller(self, controller):
		if issubclass(controller, CommandController):
			return controller(self)

	def register_controller(self, controller):
		self.cmd_controller = self.create_controller(controller)

	def create_view(self, view):
		if issubclass(view, View):
			return view()

	def register_view(self, view):
		self.view = self.create_view(view)

	def read_settings(self, filepath=None):
		if not filepath:
			filepath = self.settings_filepath
		try:
			with open(filepath) as settings_file:
				data = settings_file.read()
				_log("Loaded settings file '%s'" % filepath, level=3)
				# Remove comments since JSON doesn't allow them
				# but we want to have commentable files
				data = re.sub("#.*", "", data)
				return json.loads(data)
		except Exception as e:
			_log("Invalid settings file '%s': %s" % (filepath, str(e)))
			return {}

	def build_map(self, map_entity_ids):
		self.map = Map()
		for eid in map_entity_ids:
			entity = self.entity_factory.create_entity(eid)
			if isinstance(entity, Room):
				self.map.add_room(entity)

	def is_running(self):
		return self._is_running

	def get_character(self, eid=None, name=None):
		name = str(name).lower()
		for character in self.characters:
			if character.eid == eid:
				return character
			elif name in character.name.lower():
				return character

class View: pass

class TUI(View):
	def __init__(self, prompt=": "):
		self.prompt = prompt
		# Command history
		import atexit
		histfile = ".tworld_history"
		try:
			readline.read_history_file(histfile)
		except IOError:
			pass
		atexit.register(readline.write_history_file, histfile)

	def input(self, prompt=None):
		if prompt == None:
			prompt = self.prompt
		return input(prompt)

	def output(self, value=""):
		print(value)

def main():
	# start new game
	if len(sys.argv) > 1:
		config_path = sys.argv[1]
	else:
		config_path = "config.json"
		
	game = Game(config_path)
	game.register_controller(GameCommandController)
	game.register_view(TUI)

    # map info
	if game.settings.get("name"):
		game.view.output("Map: " + game.settings.get("name"))
	if game.settings.get("version"):
		game.view.output("Version: " + str(game.settings.get("version")))
	if game.settings.get("ask_name"):
		game.player.name = game.view.input("Your Name: ")

	# print brief help
	game.view.output()
	game.view.output("Type 'help' for help with commands.")
	
	# welcome message
	game.view.output()
	if game.settings.get("welcome"):
		game.view.output(game.settings.get("welcome"))

	# starting location
	game.map.change_room()
	game.view.output("You're in " + game.map.current_room.inspect())
	game.view.output()

	# In-game loop
	while game.is_running() and game.player.is_alive():
		# run command
		try:
			command = game.view.input()
		except KeyboardInterrupt:
			game.view.output()
			continue

		output = game.cmd_controller.execute_line(command)
		if output:
			game.view.output(output)

		# aesthetic line space
		game.view.output()

	if not game.player.is_alive():
		raise PlayerIsDead()

if __name__ == "__main__":
	while True:
		try:
			main()
		except PlayerIsDead:
			# Determine if new game should start
			print("Oh no, you died!")
			should_restart = input("Would you like to play a new game? (y/n) ")
			if should_restart.lower().startswith("y"):
				continue
			else:
				break
		except (KeyboardInterrupt, EOFError):
			print()
			break
	print("Goodbye!")

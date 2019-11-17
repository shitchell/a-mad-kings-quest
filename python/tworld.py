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
	
	def execute_line(self, line):
		line_parts = shlex.split(line)
		if len(line_parts) > 0:
			command = line_parts[0]
			args = line_parts[1:]
			func = self.get_command(command)
			if func:
				_log("running command '%s'" % command, level=4)
				return func(*args)
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

class GameCommandController(CommandController):
	def do_go(self, *args):
		"""Move through a door"""
		if len(args) == 3:
			if args[0] == "through" and args[1] == "door":
				door_id = args[2]
				# Get door from current room
				if self.game.map.current_room.has_door(door_id):
					door = self.game.map.current_room.get_door(door_id)
					if door.key and not self.game.player.inventory.contains(eid=door.key.eid):
						return "Door requires key '%s'" % door.key
					elif door.puzzle:
						# Activate puzzle
						door.puzzle.activate()
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

	def do_pickup(self, *args):
		"""Pickup an item in the current room"""
		if args:
			name = " ".join(args)
		else:
			name = None
		item = self.game.map.current_room.pop_item(name)
		if item:
			self.game.player.add_item(item)
			return "Added '%s' to inventory" % item.name
		elif name == None:
			return "No items in room!"
		elif item == None:
			return "No '%s' in room!" % name
	def do_drop(self, *args):
		"""Remove an item from the player inventory and place into the current room"""
		if args:
			name = " ".join(args)
		else:
			name = None
		item = self.game.player.pop_item(name)
		if item:
			self.game.map.current_room.add_item(item)
			return "Dropped '%s' into %s" % (item.name, self.game.map.current_room.name)
		elif name == None:
			return "No items in inventory!"
		else:
			return "No '%s' in inventory!" % name
	def do_inventory(self, *args):
		"""View items in player inventory"""
		if self.game.player.inventory:
			return ", ".join([item.name for item in self.game.player.inventory])
		else:
			return "No items in inventory!"
	def do_inspect(self, *args):
		"""Inspect a specific item in the player's inventory or the last picked up item"""
		if args:
			name = " ".join(args)
		else:
			name = None
		item = self.game.player.get_item(name)
		if item:
			return item.inspect()
		elif name:
			return "No '%s' in inventory!" % name
		else:
			return "No items in inventory!"
	def do_use(self, *args):
		"""Use a specific item in the player's inventory or the last picked up item"""
		if args:
			name = " ".join(args)
		else:
			name = None
		item = self.game.player.get_item(name)
		if item and item.can_use():
			output = ""
			if item.is_strength():
				output += "Added %i strength\n" % item.strength
				self.game.player.attack += item.strength
			if item.is_health():
				output += "Added %i health\n" % item.health
				self.game.player.health += item.health
			self.game.player.pop_item(item.name)
			return output + self.do_me()
		elif name:
			return "No '%s' in inventory!" % name
		else:
			return "No items in inventory!"
	def do_equip(self, *args):
		"""Equip a specific item in the player's inventory or the last picked up item"""
		if args:
			name = " ".join(args)
		else:
			name = None
		item = self.game.player.get_item(name)
		if item and item.can_equip():
			output = ""
			self.game.player.equip_item(item.name)
			if item.is_weapon():
				output += "Attack increased by %i\n" % item.attack
			if item.is_armor():
				output += "Armor increased by %i\n" % item.armor
			return output + self.do_me()
	def do_unequip(self, *args):
		"""Unequip the equipped item"""
		if self.game.player.equipped:
			self.game.player.unequip_item()
			return self.do_me()
		else:
			return "No item equipped!"
	def do_hint(self, *args):
		"""Get a hint for a puzzle in the current room"""
		puzzle = self.game.map.current_room.puzzle
		if puzzle:
			return puzzle.hint
		else:
			return "No puzzle found!"
	def do_solve(self, *args):
		"""Try to solve the puzzle in the current room"""
		if args:
			solution = " ".join(args)
		else:
			solution = None
		puzzle = self.game.map.current_room.puzzle
		if puzzle:
			if solution == None:
				return "That's not a terribly good guess..."
			if puzzle.solve(solution):
				self.game.map.current_room.remove_puzzle()
				msg = "Good job!"
				if puzzle.drops:
					item = self.game.create_item(puzzle.drops)
					if item:
						msg += " Something fell to the floor..."
						self.game.map.current_room.add_item(item)
				return msg
			else:
				msg = "Incorrect! "
				if puzzle.attempts:
					msg += "%i attempts remaining" % puzzle.attempts
				else:
					msg += "Puzzle removed :("
					self.game.map.current_room.remove_puzzle()
				return msg
		else:
			return "No puzzle in room!"
	def do_attack(self, *args):
		"""Try to attack the monster in the current room"""
		monster = self.game.map.current_room.monster
		player = self.game.map.player
		if monster:
			monster.damage(self.game.player.attack)
			output = "%s dealt %i damage!\n" % (player.name, player.attack)
			if monster.health <= 0:
				# Monster is dead
				self.game.map.current_room.remove_monster()
				output += "he ded\n"
			else:
				# Monster is alive and well
				# Attack player
				player.damage(monster.attack)
				# Add monster attack value
				output +="%s dealt %i damage!\n" % (monster.name, monster.attack)
				if player.health <= 0:
					# Player is dead
					raise PlayerIsDead()
				output += "Player [%i]\tMonster [%i]" % (player.health, monster.health)
		else:
			output = "No monster in room!"
		return output
	### Sue me, sue me, everybody
	def do_me(self, *args):
	### Kick me, kick me, don't you black or white me
		"""Provide player info"""
		return self.game.player.inspect()
	def do_quit(self, *args):
		"""Exit the game"""
		self.game._is_running = False

	## Admin commands
	def mod_health(self, *args):
		"""Set player health to value"""
		if args:
			self.game.player.health = int(args[0])
		return self.do_me()
	def mod_rooms(self, *args):
		"""View list of all rooms"""
		rooms = [room.uid + ": " + room.name for room in self.game.map.rooms]
		return "\n".join(rooms)
	def mod_room(self, *args):
		"""Remotely inspect any room by ID"""
		rooms = list()
		for arg in args:
			room = self.game.map.get_area_by_id(arg)
			if room:
				description = "%s: %s\n%s" % (
					room.uid,
					room.name,
					self.game.map.inspect_area(arg)
				)
				rooms.append(description)
		return "\n\n".join(rooms)
	def mod_debug(self, *args):
		"""Sets or displays debug level. Higher level increases output"""
		global DEBUG
		if args:
			try:
				DEBUG = int(args[0])
			except:
				return "Invalid debug level '%s'" % args[0]
		return "debug => " + str(DEBUG)
	def mod_items(self, *args):
		"""Return a list of items on the map and their locations"""
		room_items = list()
		for room in self.game.map.rooms:
			for item in room.items:
				room_items.append("[%s] %s: %s" % (room.uid, room.name, item.name))
		return "\n".join(room_items)
	def mod_monsters(self, *args):
		"""Return a list of monsters on the map and their locations"""
		room_monsters = list()
		for room in self.game.map.rooms:
			if room.monster:
				room_monsters.append("[%s] %s: %s" % (room.uid, room.name, room.monster.name))
		return "\n".join(room_monsters)
	def mod_eval(self, *args):
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

class Entity:
	def __init__(self, uid=None, eid=None, name="", description=""):
		self.uid = uid or uuid.uuid4().hex
		self.eid = eid
		self.name = name
		self.description = description

	def inspect(self):
		return "%s: %s" % (self.name, self.description)

class Item(Entity):
	def __init__(self, uid=None, eid=None, name="", description=""):
		super().__init__(uid, eid, name, description)
		# All items can potentially contain other items
		self.inventory = Inventory()
		self._equippable = False
		self._usable = False

	def can_equip(self):
		return self._equippable

	def can_use(self):
		return self._usable

class Key(Item): pass

class Equippable(Item):
	def __init__(self, uid=None, eid=None, name="", description=""):
		# All items can potentially contain other items
		super().__init__(uid, eid, name, description)
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

	def is_equipped(self, player):
		return self in player.equipped

class Usable(Item):
	def __init__(self, uid=None, eid=None, name="", description=""):
		# All items can potentially contain other items
		super().__init__(uid, eid, name, description)
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
	def __init__(self, uid=None, eid=None, name="", description="", damage=0):
		super().__init__(uid, eid, name, description)
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
	def __init__(self, uid=None, eid=None, name="", description="", health=0):
		super().__init__(uid, eid, name, description)
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
		self._hints = list()
		self._hint_index = 0
		try:
			self._attempts = int(attempts)
		except:
			self._attempts = None
		self._usable = True

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
			if solution == guess:
				return True
		# Incorrect guess
		try:
			self._attempts -= 1
			if self._attempts < 0:
				self._attempts = 0
		except:
			pass
		return False

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
		self._attack = attack
		self._resistance = resistance
		
		# Create an inventory and add any provided items
		self.inventory = Inventory()
		self.inventory.update(inventory)

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
	def attack(self, character=None):
		damage = self._attack
		if self.has_weapon():
			damage += self.get_weapon().damage
		if character:
			character.damage(damage)
		return damage
	
	@attack.setter
	def attack(self, value):
		try:
			self._attack = int(value)
		except:
			pass
	
	@property
	def health(self):
		return self._health
	
	@health.setter
	def health(self, value):
		try:
			self._health = int(value)
		except:
			return	
		if self._health > 100:
			self._health = 100
		elif self._health < 0:
			self._health = 0
		if self._health == 0:
			_log("Character '%s' is dead" % self.name, level=2)
		else:
			_log("Set '%s' health to '%i'" % (self.name, self.health), level=2)
	
	def damage(self, value):
		try:
			self.health -= value
		except:
			_log("invalid damage '%s'" % value)
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

	## Custom inspect command
	def inspect(self):
		description = "%s | %i 🗡️ | %i ❤" % (
			self.name,
			self.attack,
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
	
	def __repr__(self):
		return self.name

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
		for monster in self._monsters:
			if monster.eid == eid:
				self._monsters.remove(monster)
			elif name in monster.name.lower():
				self._monsters.remove(monster)

	def get_monster(self):
		# If a boss monster exists, return the boss monster
		for monster in self._monsters:
			if monster.is_boss():
				return monster
		# Else, return a random normal monster or no monster
		return random.choice(self._monsters + [None])

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
		if eid:
			eid = str(eid)
			_log("Creating entity '%s'" % eid, level=4)
			entity_dict = self._entities.get(eid)
			if entity_dict:
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
			damage = entity_dict.get("equip", dict()).get("armor")
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
			health = entity_dict.get("health")
		)

	# Create a key object
	def _create_key(self, entity_dict):
		# eid, name, description
		return Key(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description")
		)

	# Create a monster object
	def _create_mon(self, entity_dict):
		# eid, name, description, health, attack, resistance, armor, weapon, inventory
		# Create the armor if it exists
		armor = self.create_entity(entity_dict.get("armor"))
		# Create the weapon if it exists
		weapon = self.create_entity(entity_dict.get("weapon"))
		# Create any items in the inventory
		items = self.create_entities(entity_dict.get("inventory"))
		inventory = Inventory(items)
		return Monster(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			health = entity_dict.get("health"),
			attack = entity_dict.get("attack"),
			resistance = entity_dict.get("resistance"),
			armor = armor,
			weapon = weapon,
			inventory = inventory,
			is_boss = entity_dict.get("is_boss")
		)

	# Create a puzzle object
	def _create_puz(self, entty_dict):
		# eid, name, description, solutions, hints, attempts
		return Puzzle(
			eid = entity_dict.get("eid"),
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
			damage = entity_dict.get("equip", dict()).get("attack")
		)

class Map:
	def __init__(self, rooms=list()):
		self._rooms = list()
		self.current_room = None
		for room in rooms:
			self._add_room(room)

	## Rooms
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
		rooms = list()
		if name:
			name = str(name).lower()
		for room in self._rooms:
			if name and name in room.name.lower():
				rooms.append(room)
			elif door and room.has_door(door):
				rooms.append(room)
		return rooms

	def change_room(self, eid=None, name=None):
		if not eid and not name:
			room = self.get_random_room()
		else:
			room = self.get_room(eid, name)
		if room:
			if isinstance(self.current_room, Room):
				self.current_room.visited = True
			self.current_room = room
			room.enter()

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

def main():
	# start new game
	if len(sys.argv) > 1:
		config_path = sys.argv[1]
	else:
		config_path = "config.json"
		
	game = Game(config_path)
	game.register_controller(GameCommandController)

    # map info
	if game.settings.get("name"):
		print("Map: " + game.settings.get("name"))
	if game.settings.get("version"):
		print("Version: " + str(game.settings.get("version")))
	if game.settings.get("ask_name"):
		game.player.name = input("Your Name: ")

	# print brief help
	print()
	print("Type 'help' for help with commands.")
	
	# welcome message
	print()
	if game.settings.get("welcome"):
		print(game.settings.get("welcome"))

	# starting location
	game.map.change_room()
	print("You're in " + game.map.current_room.inspect())
	print()

	# In-game loop
	while game.is_running() and game.player.is_alive():
		# run command
		try:
			command = input(": ")
		except KeyboardInterrupt:
			print()
			continue

		output = game.cmd_controller.execute_line(command)
		if output:
			print(output)

		# aesthetic line space
		print()

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

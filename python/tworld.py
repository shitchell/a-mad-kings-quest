import os
import re
import sys
import uuid
import json
import time
import shlex
import pickle
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
	try:
		caller_class = caller.f_locals["self"].__class__.__qualname__
	except:
		caller_class = "__main__"
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
				_log("command output:", output, level=5)
				if output:
					return str(output)
				return
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
	def _retrieve_items(self, inventory):
		items = dict()
		for item in inventory.get_items():
			items[item.name] = item
			if item.inventory.size() > 0:
				inner_items = self._retrieve_items(item.inventory)
				items.update(inner_items)
		return items

	def _retrieve_local_entities(self, room_inventory=None, player_inventory=None, monster_inventory=None, monster=None):
	    # If no arguments are True, assume all are True
		args = [room_inventory, player_inventory, monster_inventory, monster]
		if True in args:
			room_inventory = bool(room_inventory)
			player_inventory = bool(player_inventory)
			monster_inventory = bool(monster_inventory)
			monster = bool(monster)
		items = dict()
		if room_inventory != False:
			items.update(self._retrieve_items(self.game.map.current_room.inventory))
		if player_inventory != False:
			items.update(self._retrieve_items(self.game.player.inventory))
		if monster_inventory != False and self.game.map.current_room.monster:
			items.update(self._retrieve_items(self.game.map.current_room.monster.inventory))
		if monster != False and self.game.map.current_room.monster:
			items[self.game.map.current_room.monster.name] = self.game.map.current_room.monster
		return items

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
						output += self.game.player.inspect_stats()
						return output
					door = self.game.map.current_room.get_door(door_id)
					if door.key and not self.game.player.inventory.contains(eid=door.key.eid):
						return "Door requires key '%s'" % door.key.name
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
							if controller.is_active():
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

	@CommandController.admin
	def do_look(self, *args):
		"""Describe the current location"""
		return "You're in " + self.game.map.current_room.inspect()

	def do_inspect(self, *args):
		"""usage: inspect room\nusage: inspect monster_name\nusage: inspect item_name\nInspect the current room, a monster in the room, or any item in the room, player inventory, or monster inventory"""
		if args:
			name = " ".join(args)
			if name == "room":
				return self.game.map.current_room.inspect()
			# Collect all inspectable items
			items = self._retrieve_local_entities()
			_log("Inspectable items:", items, level=4)
			# Determine if name in items
			for key in items:
				if name.lower() in key.lower():
					return items[key].inspect()
			return "Could not find '%s'" % name
		return self.game.map.current_room.inspect()

	def do_open(self, *args):
		"""usage: open chest_name\nOpen a chest in the room or player's inventory"""
		if args:
			name = " ".join(args)
			# Collect all inspectable items
			items = self._retrieve_local_entities(room_inventory=True, player_inventory=True)
			_log("Chest candidates:", items, level=4)
			# Determine if name in items
			for key in items:
				if name.lower() in key.lower():
					# Matched chest
					chest = items[key]
					output = ""
					if chest.is_locked():
						# Check to see if user has key
						if self.game.player.inventory.contains(eid=chest.key.eid):
							chest.is_locked(False)
							output += "Unlocked chest!\n"
					output += chest.inspect()
					return output
			return "Could not find '%s'" % name

	def do_use(self, *args):
		"""usage: use item_name\nUse a food item in the player's inventory"""
		if args:
			name = " ".join(args)
			# Collect all items
			items = self._retrieve_local_entities(player_inventory=True)
			_log("Use candidates:", items, level=4)
			# Determine if name in items
			for key in items:
				if name.lower() in key.lower():
					# Matched item
					item = items[key]
					# Determine if item is usable
					if not item.can_use():
						return "You cannot use '%s'" % item.name
					# Use the item
					item.use(self.game.player)
					return "Player eats '%s' and heals %i health to %i" % (item.name, item.health, self.game.player.health)
			return "Could not find '%s'" % name

	def do_equip(self, *args):
		"""usage: equip item_name\nEquip an armor or weapon in the player's inventory"""
		if args:
			name = " ".join(args)
			# Collect all items
			items = self._retrieve_local_entities(player_inventory=True)
			_log("Equip candidates:", items, level=4)
			# Determine if name in items
			for key in items:
				_log("Comparing", name.lower(), "in", key.lower(), level=5)
				if name.lower() in key.lower():
					# Matched item
					item = items[key]
					# Determine if item is equipable
					if not item.can_equip():
						return "You cannot equip '%s'" % item.name
					# Equip the item
					item.equip(self.game.player)
					return "The player equip %s" % item.name
			return "Could not find '%s'" % name

	def do_unequip(self, *args):
		"""usage: unequip item_name\nUnequip an armor or weapon"""
		if args:
			name = " ".join(args)
			# Collect all items
			items = self._retrieve_local_entities(player_inventory=True)
			_log("Unequip candidates:", items, level=4)
			# Determine if name in items
			for key in items:
				_log("Comparing", name.lower(), "in", key.lower(), level=5)
				if name.lower() in key.lower():
					# Matched item
					item = items[key]
					# Determine if item is equipped
					if item.can_equip() and not item.is_equipped(self.game.player):
						return "'%s' is not equipped" % item.name
					elif not item.can_equip():
						return "'%s' is not an equippable item" % item.name
					elif item.can_equip and item.is_equipped(self.game.player):
						# Unequip the item
						item.unequip(self.game.player)
						return "The player unequips %s" % item.name
			return "Could not find '%s'" % name

	def do_pickup(self, *args):
		"""usage: pickup item_name\nPickup an item in the current room or chest"""
		if args:
			name = " ".join(args)
			# Collect all items
			items = self._retrieve_local_entities(room_inventory=True)
			_log("Pickup candidates:", items, level=4)
			# Determine if name in items
			for key in items:
				if name.lower() in key.lower():
					# Matched item
					item = items[key]
					# Remove from room inventory
					self.game.map.current_room.inventory.pop(eid=item.eid)
					self.game.player.inventory.add(item)
					# Display inventory
					output = "Player picks up '%s'\n" % item.name
					output += self.game.player.inspect()
					return output
			return "Could not find '%s'" % name

	def do_drop(self, *args):
		"""usage: pickup item_name\nPickup an item in the current room or chest"""
		if args:
			name = " ".join(args)
			# Collect all items
			items = self._retrieve_local_entities(player_inventory=True)
			_log("Drop candidates:", items, level=4)
			# Determine if name in items
			for key in items:
				if name.lower() in key.lower():
					# Matched item
					item = items[key]
					# Remove from room inventory
					self.game.player.inventory.pop(eid=item.eid)
					self.game.map.current_room.inventory.add(item)
					# Display inventory
					output = "'%s' dropped\n" % item.name
					output += self.game.player.inspect()
					return output
			return "Could not find '%s'" % name

	def do_access(self, *args):
		"""usage: access inventory\nView items in player inventory"""
		if args and args[0] == "inventory":
			if self.game.player.inventory.size() > 0:
				return ", ".join([item.name for item in self.game.player.inventory.get_items()])
			else:
				return "No items in inventory!"

	@CommandController.admin
	def do_view(self, *args):
		"""usage: view equipment\nView currently equipped items"""
		if args and args[0] == "equipment":
			if self.game.player.equipped:
				return ", ".join([item.name for item in self.game.player.equipped])
			else:
				return "No equipped items!"

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
				output += "You defeated '%s'!" % monster.name
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

	def do_save(self, *args):
		"""usage: save\nsave save_name\nSave the current game state"""
		if args:
			filename = "_".join(args)
		else:
			filename = self.game.player.name
		filepath = self.game.save(filename)
		if filepath:
			return "Saved game to '%s'" % filepath
		return "Failed to save game"

	def do_load(self, *args):
		"""usage: load\nload save_name\nRevert to the last save point or load a particular saved game"""
		if args:
			filename = "_".join(args)
		else:
			filename = self.game.player.name
		g = self.game.load(filename)
		if isinstance(g, Game):
			self.game = g
			return "Loaded game '%s'" % filename
		return "Failed to load game '%s'" % filename

	## Admin commands
	@CommandController.admin
	def do_set_health(self, *args):
		"""Set player health to value"""
		if args:
			self.game.player.health = int(args[0])
		return self.game.player.inspect_stats()

	@CommandController.admin
	def do_set_attack(self, *args):
		"""Set player attack to value"""
		if args:
			self.game.player._base_attack = int(args[0])
		return self.game.player.inspect_stats()

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
	def do_teleport(self, *args):
		"""Teleport to a remote room"""
		if args:
			eid = args[0]
			if self.game.map.change_room(eid=eid):
			    return self.game.map.current_room.inspect()

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
			return output + "\n" + self.game.player.inspect()
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

	def inspect(self):
		output = super().inspect()
		for item in self.inventory.get_items():
			output += "\n- " + item.name
		return output


class Key(Item): pass

class Chest(Item):
	def __init__(self, uid=None, eid=None, name="", description="", drop_chance=None, key=None):
		super().__init__(uid, eid, name, description)
		self._key = key
		self._is_locked = True

	@property
	def key(self):
		return self._key

	def is_locked(self, value=None):
		if isinstance(value, bool):
			self._is_locked = value
		return self._is_locked

	def requires_key(self):
		return isinstance(self._key, Key)

	def inspect(self):
		if self.is_locked():
			return "%s [locked: %s]" % (self.name, self._key.name)
		else:
			return super().inspect()

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
		if inventory.contains(eid=self.eid):
			# Call the _on_use method. Inheriting classes
			# should overwrite _on_use() rather than use()
			self._on_use(player, inventory)
			# Remove the food item from the inventory
			inventory.pop(eid=self.eid)

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
	def inspect_stats(self):
		return "%s | %i 🗡️ | %i ❤" % (
			self.name,
			self.get_attack_damage(),
			self.health
		)

	def _retrieve_item_names(self, inventory, depth=1):
		names = list()
		for item in inventory.get_items():
			name = "- "*depth
			name += item.name
			if item.is_equipped(self):
				name += " [equipped]"
			names.append(name)
			if item.inventory.size() > 0:
				if isinstance(item, Chest) and item.is_locked():
					continue
				else:
					subitems = self._retrieve_item_names(item.inventory, depth+1)
					names.extend(subitems)
		return names

	def inspect(self):
		description = self.inspect_stats()
		if self.description:
			description += "\n" + self.description
		if self.inventory.size() > 0:
			names = self._retrieve_item_names(self.inventory)
			for name in names:
				description += "\n" + name
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
		description = "%s: %s" % (self.name, self.description)
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
		key_eid = entity_dict.get("key")
		key = self.create_entity(key_eid)
		chest = Chest(
			eid = entity_dict.get("id"),
			name = entity_dict.get("name"),
			description = entity_dict.get("description"),
			key = key
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
			health = entity_dict.get("use", dict()).get("health"),
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
	# pylint: disable=too-many-instance-attributes
	def __init__(self, settings_filepath="config.json", name=None):
		# Default attributes
		self._filepaths = {
			"config": None,
			"map": None,
			"entities": list()
		}
		self._is_won = False
		self._is_running = True
		self._name = name
		self._save_extension = ".tsave"
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

		# Create character
		self.player = Player("me")
		self.characters.append(self.player)

		# Build game map
		self.build_map(map_entity_ids)

	@property
	def name(self):
		return str(self._name or "tworld")

	@property
	def save_extension(self):
		return str(self._save_extension)

	def settings_filepath(self, filename=None):
		if not isinstance(filename, str):
			filename = self.name
		return filename + self.save_extension

	def save(self, filename=None):
		filepath = self.settings_filepath(filename)
		try:
			with open(filepath, "wb") as f:
				pickle.dump(self, f)
			return filepath
		except:
			pass

	def load(self, filename=None):
		filepath = self.settings_filepath(filename)
		try:
			with open(filepath, "rb") as f:
				return pickle.load(f)
		except:
			pass
		return False

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

	def is_running(self, value=None):
		if isinstance(value, bool):
			self._is_running = value
		return self._is_running

	def is_won(self, value=None):
		if isinstance(value, bool):
			if self.is_won() == False and value == True:
				message = self.settings.get("win", dict()).get("message")
				if message:
					self.view.output(message)
			self._is_won = value
		return self._is_won

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
	room_id = game.settings.get("start")
	if not game.map.change_room(eid=room_id):
		game.map.change_room()
	game.view.output(game.map.current_room.inspect())
	game.view.output()

	# Game winning condition
	win_condition = game.settings.get("win")
	_log("Winning condition", win_condition, level=2)

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
			if win_condition.get("output_contains"):
				_log("Checking to see if output contains", win_condition.get("output_contains"), level=6)
				if win_condition.get("output_contains") in output:
					# The game is won!
					game.is_won(True)
			if win_condition.get("output_matches"):
				if win_condition.get("output_matches") == output:
					# The game is won!
					game.is_won(True)

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

import os
import re
import sys
import json
import time
import shlex
import string
import string
import random
import hashlib
try:
	import readline
except:
	import pyreadline as readline

class InvalidSettingsFile(Exception): pass
class InvalidDirection(Exception): pass
class PlayerIsDead(Exception): pass

# Debug level
# Higher level increases output
DEBUG = 4
def _log(*args, level=3, **kwargs):
	global DEBUG
	if DEBUG and DEBUG >= level:
		timestamp = time.strftime("[%Y-%m-%d_%H:%M:%S] ")
		print(timestamp, *args)

def _md5(text):
	return hashlib.md5(text.encode("utf-8")).hexdigest()

class Game:
	def __init__(self, settings_filepath="Rooms.txt"):
		self.settings_filepath = settings_filepath
		self.settings = self.read_settings(settings_filepath)
		self._is_running = True
		self.cmd_controller = CommandController(self)
		self.player = Player()
		self.characters = list()
		self.characters.append(self.player)
		self.build_map()
	def read_settings(self, filepath=None):
		if not filepath:
			filepath = self.settings_filepath
		try:
			with open(filepath) as settings_file:
				data = settings_file.read()
				# Remove comments since JSON doesn't allow them
				# but we want to have commentable files
				data = re.sub("#.*", "", data)
				return json.loads(data)
		except Exception as e:
			_log("Invalid settings file '%s': %s" % (filepath, str(e)))
			return {}
	def build_map(self):
		if not "areas" in self.settings:
			raise InvalidSettingsFile("No areas in '%s'" % self.settings_filepath)
		self.map = Map(self.settings["areas"])
		self.add_items()
		self.add_puzzles()
		self.add_monsters()
	def create_item(self, name):
		for item in self.settings.get("items", list()):
			if item.get("name") == name:
				return Item(item)
	def add_items(self, filepath="Items.txt"):
		settings = self.read_settings(filepath)
		if settings:
			self.settings.update(settings)
		for item in settings.get("items", list()):
			_log("adding", item, level=4)
			item_location = item.get("area")
			if item_location:
				if item_location == "random":
					room = self.map.get_random_area()
				else:
					room = self.map.get_area_by_id(item_location)
				# If that location exists on our map...
				if room:
					try:
						item = Item(item)
					except Exception:
						# Invalid item
						_log("invalid item '%s'" % item, level=3)
						continue
					room.add_item(item)
					_log("added %s to %s" % (
						item.name,
						room.name
					), level=3)
				else:
					_log("%s skipped" % item, level=3)
			else:
				_log("%s skipped" % item)
	def add_puzzles(self, filepath="Puzzles.txt"):
		try:
			settings = self.read_settings(filepath)
		except Exception as e:
			raise InvalidSettingsFile("%s: %s" % (filepath, str(e)))
		self.settings.update(settings)
		for puzzle in settings.get("puzzles", list()):
			_log("adding", puzzle, level=4)
			puzzle_location = puzzle.get("area")
			room = None
			if puzzle_location:
				if puzzle_location == "random":
					room = self.map.get_random_area()
				else:
					room = self.map.get_area_by_id(puzzle_location)
			if room:
				try:
					puzzle = Puzzle(puzzle)
				except Exception:
					# Invalid puzzle
					_log("invalid puzzle '%s'" % puzzle, level=3)
					continue
				room.add_puzzle(puzzle)
				_log("added %s to %s" % (
					puzzle.description,
					room.name
				), level=3)
	def add_monsters(self, filepath="Monsters.txt"):
		try:
			settings = self.read_settings(filepath)
		except Exception as e:
			raise InvalidSettingsFile("%s: %s" % (filepath, str(e)))
		self.settings.update(settings)
		for monster in settings.get("monsters", list()):
			_log("adding", monster, level=4)
			monster_location = monster.get("area", "random")
			room = None
			if monster_location:
				if monster_location == "random":
					room = self.map.get_random_area()
				else:
					room = self.map.get_area_by_id(monster_location)
			if room:
				try:
					monster = Monster(monster)
				except Exception:
					# Invalid monster
					pri()
					_log("invalid monster '%s'" % monster, level=3)
					continue
				room.add_monster(monster)
				self.characters.append(monster)
				_log("added %s to %s" % (
					monster.name,
					room.name
				), level=3)
	def is_running(self):
		return self._is_running
	def execute_line(self, line):
		return self.cmd_controller.execute_line(line)
	def get_character(self, name):
		for character in characters:
			if character.name == name:
				return character
	def initiate_attack(self, attacker, victim):
		pass

class CommandController:
	def __init__(self, game):
		self.game = game
	def execute_line(self, line):
		line_parts = shlex.split(line)
		if len(line_parts) > 0:
			command = line_parts[0].lower()
			args = line_parts[1:]
			func = None
			if hasattr(self, "do_" + command):
				func = getattr(self, "do_" + command)
				_log("running player command '%s'" % command, level=4)
			elif hasattr(self, "mod_" + command):
				func = getattr(self, "mod_" + command)
				_log("running admin command '%s'" % command, level=4)
			else:
				return "%s: command not found" % command
			if func:
				return func(*args)
	def do_help(self, *args, **kwargs):
		"""Prints help wth the game or a specific command"""
		if args:
			cmd = args[0]
			if hasattr(self, "do_" + cmd):
				return getattr(self, "do_" + cmd).__doc__
			elif hasattr(self, "mod_" + cmd):
				return getattr(self, "mod_" + cmd).__doc__
		else:
			commands = filter(lambda x: x.startswith("do_"), dir(self))
			commands = [x[3:] for x in commands]
			return "Commands: " + ", ".join(commands)
	def do_move(self, *args):
		"""Move in a direction indicated by *asterisks*"""
		if args:
			direction = args[0].lower()
			success = self.game.map.move_player(direction)
			if not success:
				return "You cannot move that way!"
			else:
				return "You're in " + self.game.map.inspect_area(self.game.map.current_room.uid)
		else:
			return "~You do a little dance in place~"
	def do_look(self, *args):
		"""Describe the current location"""
		return "You're in " + self.game.map.inspect_area(self.game.map.current_room.uid)
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
		"""Inspect a specific item in the player's inventory, a monster, or the last picked up item"""
		if args:
			name = " ".join(args)
		else:
			name = None
		item = self.game.player.get_item(name) or self.game.current_room.monster
		if item:
			return item.inspect()
		elif name:
			return "No '%s'!" % name
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

class Character:
	def __init__(self, uid=None, name=None, health=100, description="", attack=10, resistance=0, armor=0, weapon=None, inventory=list()):
		self.uid = uid
		if not name:
			name = "Character%i" % random.randrange(1111,9999)
		self.name = name
		self.inventory = inventory
		self.equipped = {"weapon": weapon, "armor": armor}
		self.health = health
		self.description = description
		self._attack = attack
		self._resistance = resistance
	@property
	def attack(self, character=None):
		damage = self._attack
		if self.equipped.get("weapon"):
			damage += self.equipped.get("weapon").attack
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
	def add_item(self, item):
		self.inventory.append(item)
		_log("Added '%s' to '%s' inventory" % (item.name, self.name), level=2)
	def get_item(self, name=None):
		if name:
			for item in self.inventory:
				if item.name.lower() == name.lower():
					return item
		elif name == None and len(self.inventory) > 0:
			return self.inventory[-1]
	def pop_item(self, name=None):
		item = self.get_item(name)
		if item:
			self.inventory.remove(item)
			if item == self.equipped:
				self.equipped = None
			_log("Removed '%s' from '%s' inventory" % (item.name, self.name), level=2)
			return item
	def get_items(self):
		return self.inventory
	def equip_item(self, name):
		item = self.get_item(name)
		if item and item.can_equip():
			# Remove any previously equipped items
			self.unequip_item()
			self.equipped = item
	def unequip_item(self):
		self.equipped = None
	def is_alive(self):
		return self.health > 0
	def adjust_health(self, value):
		"""Change health by value"""
		self.set_health(self.health + value)
	def inspect(self):
		description = "%s | %i 🗡️ | %i ❤" % (
			self.name,
			self.attack,
			self.health
		)
		if self.description:
			description += "\n" + self.description
		if self.get_items():
			for item in self.get_items():
				description += "\n- " + item.name
				if item == self.equipped:
					description += " [equipped]"
		return description
	def __repr__(self):
		return self.name

class Player(Character): pass
class Monster(Character):
	def __init__(self, config):
		super().__init__(
			config.get("uid"),
			config.get("name"),
			config.get("health"),
			config.get("description"),
			config.get("attack"),
			config.get("resistance"),
			config.get("armor"),
			config.get("weapon"),
			config.get("inventory")
		)

class Map:
	def __init__(self, config):
		self.rooms = list()
		self.current_room = None
		self._load_rooms(config)
	def _load_rooms(self, areas):
		for area in areas:
			room = Room(area)
			self._add_room(room)
	def _add_room(self, room):
		self.rooms.append(room)
	def get_random_area(self):
		return random.choice(self.rooms)
	def get_area_by_id(self, uid):
		for room in self.rooms:
			if room.uid == uid:
				return room
	def get_area_by_name(self, name):
		for room in self.rooms:
			if room.name.lower() == name.lower():
				return room
	def move_player(self, direction):
		if self.current_room.has_direction(direction):
			destination_uid = self.current_room.get_direction(direction)
			if destination_uid:
				self.current_room.visited = True
				self.teleport_player(destination_uid)
				return True
			else:
				raise InvalidDirection(direction)
		return False
	def teleport_player(self, uid=None):
		if not uid:
			uids = [room.uid for room in self.rooms]
			uid = random.choice(uids)
		destination = self.get_area_by_id(uid)
		if destination:
			if self.current_room:
				self.current_room.visited = True
			self.current_room = destination
			return self.inspect_area(self.current_room.uid)
	def inspect_area(self, uid):
		area = self.get_area_by_id(uid)
		description = area.description
		if area.items:
			description += "\nItems:"
			for item in area.items:
				description += "\n - " + item.name
		if area.puzzle:
			description += "\nPuzzle:"
			for line in area.puzzle.description.split("\n"):
				description += "\n - " + line
		if area.directions:
			description += "\nDirections:"
			for direction in area.directions:
				destination_uid = area.directions[direction]
				destination = self.get_area_by_id(destination_uid)
				description += "\n - A %s is to the *%s*." % (destination.name, direction)
		if area.monster:
			description += "\nMonster:"
			description += "\n - %s" % area.monster.name
		if area.visited:
			description += "\nYou've been here before."
		return description

class Room:
	def __init__(self, config):
		self.uid = config["id"]
		self.name = config["name"]
		self.type = config["type"]
		self.description = config["description"]
		self.directions = config["directions"]
		self.visited = False
		self.items = list()
		self.puzzle = None
		self.monster = None
	def _sanitize_directions(self):
		# Ensure that all directions are lowercase
		for direction in self.directions:
			if direction != direction.lower():
				self.directions[direction.lower()] = self.directions[direction]
				del self.directions[direction]
	def add_direction(self, direction, destination):
		self.directions[direction.lower()] = destination
	def get_directions(self):
		return [x.lower() for x in self.directions]
	def has_direction(self, direction):
		return direction.lower() in self.get_directions()
	def get_direction(self, direction):
		# Return the given direction, else the current room if no such direction exists
		return self.directions.get(direction.lower(), self)
	def add_item(self, item):
		self.items.append(item)
	def get_item(self, name):
		for item in self.items:
			if item.name.lower() == name.lower():
				return item
	def pop_item(self, name=None):
		item = None
		if name:
			item = self.get_item(name)
		elif self.items:
			item = self.items[0]
		if item:
			self.items.remove(item)
			return item
	def add_puzzle(self, puzzle):
		self.puzzle = puzzle
	def remove_puzzle(self):
		self.puzzle = None
	def get_puzzle(self):
		return self.puzzle
	def add_monster(self, monster):
		self.monster = monster
	def remove_monster(self):
		self.monster = None
	def get_monster(self):
		return self.monster

class Item:
	def __init__(self, config):
		self.name = config["name"]
		self.description = config["description"]
		self._can_equip = False
		self._can_use = False
		self.attack = config.get("equip", dict()).get("attack")
		self.armor = config.get("equip", dict()).get("armor")
		self.health = config.get("use", dict()).get("health")
		self.strength = config.get("use", dict()).get("strength")
		_log("creating item '%s'" % self.name, level=2)
	@property
	def health(self):
		return self._health
	@health.setter
	def health(self, value):
		try:
			self._health = int(value)
		except:
			self._health = 0
		if self._health != 0:
			self._can_use = True
	def is_health(self):
		return self._health != 0
	@property
	def strength(self):
		return self._strength
	@strength.setter
	def strength(self, value):
		try:
			self._strength = int(value)
		except:
			self._strength = 0
		if self._strength != 0:
			self._can_use = True
	def is_strength(self):
		return self._strength != 0
	@property
	def attack(self):
		return self._attack
	@attack.setter
	def attack(self, value):
		try:
			self._attack = int(value)
		except:
			self._attack = 0
		if self._attack < 0:
			self._attack = 0
		elif self._attack > 0:
			self._can_equip = True
	def is_weapon(self):
		return self.attack != 0
	@property
	def armor(self):
		return self._armor
	@armor.setter
	def armor(self, value):
		try:
			self._armor = int(value)
		except:
			self._armor = 0
		if self._armor < 0:
			self._armor = 0
		elif self._armor > 0:
			self._can_equip = True
	def is_armor(self):
		return self._armor != 0
	def can_equip(self):
		return self._can_equip
	def can_use(self):
		return self._can_use
	def inspect(self):
		description = "%s: %s" % (self.name, self.description)
		if self.can_use() or self.can_equip():
			description += "\nIt looks like you can "
		if self.can_use():
			description += "use "
		if self.can_use() and self.can_equip():
			description += "or "
		if self.can_equip():
			description += "equip "
		if self.can_use() or self.can_equip():
			description += "this item!"
		return description

class Puzzle:
	def __init__(self, config):
		self.description = config["description"]
		self.solutions = config["solutions"]
		self.hint = config.get("hint")
		self.attempts = config.get("attempts")
		self.drops = config.get("drops")
		_log("creating puzzle '%s'" % self.description, level=2)
	def solve(self, solution):
		# lowercase solution
		solution = solution.lower()
		# remove punctuation
		solution = solution.translate(str.maketrans(dict.fromkeys(string.punctuation)))
		md5 = _md5(solution)
		if md5 in self.solutions:
			return True
		else:
			if self.attempts != None:
				self.attempts -= 1
			return False

def main():
	# start new game
	game = Game()

    # map info
	print("Map: " + game.settings["settings"]["name"])
	print("Version: " + game.settings["settings"]["version"])
	game.player.name = input("Your Name: ")

	# print brief help
	print()
	print("Type 'help' for help with commands.")
	
	# welcome message
	print()
	print(game.settings["settings"]["welcome"])

	# starting location
	game.map.teleport_player()
	print("You're in " + game.map.inspect_area(game.map.current_room.uid))
	print()
	
	# In-game loop
	while game.is_running() and game.player.is_alive():
		# run command
		try:
			command = input(": ")
		except KeyboardInterrupt:
			print()
			continue
		
		output = game.execute_line(command)
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
	sys.exit(0)
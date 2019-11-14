import os
import re
import sys
import json
import time
import shlex
import string
import random
import hashlib
import pyreadline

class InvalidSettingsFile(Exception): pass
class InvalidDirection(Exception): pass

DEBUG = False
def _log(*args, **kwargs):
	if DEBUG:
		timestamp = time.strftime("[%Y-%m-%d_%H:%M:%S] ")
		print(timestamp, *args)

def _md5(text):
	return hashlib.md5(text.encode("utf-8")).hexdigest()

class Game:
	def __init__(self, settings_filepath="Rooms.txt"):
		self.settings_filepath = settings_filepath
		self.settings = self.read_settings(settings_filepath)
		self.build_map()
		self._is_running = True
		self.cmd_controller = CommandController(self)
		self.player = Player()
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
			raise InvalidSettingsFile("%s: %s" % (filepath, str(e)))
	def build_map(self):
		if not "areas" in self.settings:
			raise InvalidSettingsFile("No areas in '%s'" % self.settings_filepath)
		self.map = Map(self.settings["areas"])
		self.add_items()
		self.add_puzzles()
	def create_item(self, name):
		for item in self.settings.get("items", list()):
			_log(item.get("name"),"=>", name)
			if item.get("name") == name:
				return Item(item)
	def add_items(self, filepath="Items.txt"):
		try:
			settings = self.read_settings(filepath)
		except Exception as e:
			raise InvalidSettingsFile("%s: %s" % (filepath, str(e)))
		self.settings.update(settings)
		for item in settings.get("items", list()):
			_log("adding", item)
			item_location = item.get("area")
			if item_location:
				room = self.map.get_area_by_id(item_location)
				# If that location exists on our map...
				if room:
					try:
						item = Item(item)
					except Exception:
						# Invalid item
						continue
					room.add_item(item)
					_log("added %s to %s" % (
						item.name,
						room.name
					))
				else:
					_log("%s skipped" % item)
			else:
				_log("%s skipped" % item)
	def add_puzzles(self, filepath="Puzzles.txt"):
		try:
			settings = self.read_settings(filepath)
		except Exception as e:
			raise InvalidSettingsFile("%s: %s" % (filepath, str(e)))
		self.settings.update(settings)
		for puzzle in settings.get("puzzles", list()):
			_log("adding", puzzle)
			puzzle_location = puzzle.get("area")
			if puzzle_location:
				room = self.map.get_area_by_id(puzzle_location)
			else:
				room = self.map.get_random_area()
			if room:
				try:
					puzzle = Puzzle(puzzle)
				except Exception:
					# Invalid puzzle
					continue
				room.add_puzzle(puzzle)
				_log("added %s to %s" % (
					puzzle.description,
					room.name
				))
	def is_running(self):
		return self._is_running
	def execute_line(self, line):
		return self.cmd_controller.execute_line(line)

class CommandController:
	def __init__(self, game):
		self.game = game
	def execute_line(self, line):
		line_parts = shlex.split(line)
		if len(line_parts) > 0:
			command = line_parts[0]
			args = line_parts[1:]
			if hasattr(self, "do_" + command):
				func = getattr(self, "do_" + command)
				return func(*args)
			else:
				return "%s: command not found" % command
	def do_help(self, *args, **kwargs):
		"""Prints help wth the game or a specific command"""
		if args:
			cmd = args[0]
			if hasattr(self, "do_" + cmd):
				return getattr(self, "do_" + cmd).__doc__
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
		"""Inspect a specific item in the player's inventory or the last picked up item"""
		if args:
			name = " ".join(args)
		else:
			name = None
		item = self.game.player.get_item(name)
		if item:
			if args:
				return item.description
			else:
				return "%s: %s" % (item.name, item.description)
		elif name:
			return "No '%s' in inventory!" % name
		else:
			return "No items in inventory!"
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
					msg += " Something fell to the floor..."
					item = self.game.create_item(puzzle.drops)
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
	### Sue me, sue me, everybody
	def do_me(self, *args):
	### Kick me, kick me, don't you black or white me
		"""Provide player info"""
		description = "%s | %i ❤" % (
			self.game.player.name,
			self.game.player.health
		)
		for item in self.game.player.get_items():
			description += "\n- " + item.name
		return description
	def do_quit(self):
		"""Exit the game"""
		self.game._is_running = False

class Player:
	def __init__(self, name="Player"):
		self.name = name
		self.inventory = list()
		self.health = 100
	def add_item(self, item):
		self.inventory.append(item)
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
			return item
	def get_items(self):
		return self.inventory
	def __repr__(self):
		return self.name

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

class Item:
	def __init__(self, config):
		self.name = config["name"]
		self.description = config["description"]

class Puzzle:
	def __init__(self, config):
		self.description = config["description"]
		self.solutions = config["solutions"]
		self.hint = config.get("hint")
		self.attempts = config.get("attempts")
		self.drops = config.get("drops")
	def solve(self, solution):
		md5 = _md5(solution.lower())
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
	while game.is_running():
		# run command
		command = input(": ")
		output = game.execute_line(command)
		if output:
			print(output)

		# aesthetic line space
		print()

	print("Goodbye!")

if __name__ == "__main__":
	try:
		main()
	except (KeyboardInterrupt, EOFError):
		print()
		print("exiting application")
		sys.exit(1)
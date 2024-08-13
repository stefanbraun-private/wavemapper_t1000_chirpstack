

import config as cfg

# based on examples on https://docs.ponyorm.org/firststeps.html
from pony.orm import *

# example with datetime: https://github.com/ponyorm/pony/issues/319
import datetime
import h3



db = Database()
# SQLite in-memory versus permanent storage:
#db.bind(provider='sqlite', filename=':memory:')
db.bind(provider='sqlite', filename=cfg.DATABASE_FILENAME, create_db=True)


class Exploration(db.Entity):
	cell = PrimaryKey(str)
	score = Required(int, default=0)
	updated_at = Required(datetime.datetime, default=datetime.datetime.utcnow)

class Tracker(db.Entity):
	dev_eui = PrimaryKey(str)
	device_name = Required(str, default="Noname")
	score = Required(int, default=0)


sql_debug(False)
db.generate_mapping(create_tables=True)


@db_session
def get_trackers():
	trackers = select(t for t in Tracker)
	return [(t.device_name, t.dev_eui, t.score) for t in trackers]


@db_session
def get_explorations():
	explorations = select(e for e in Exploration if e.score > 0)
	return [(e.cell, e.score) for e in explorations]


@db_session
def add_exploration(dev_eui, device_name, lat, lng, updated_at):
	try:
		tracker = Tracker[dev_eui]
	except pony.orm.core.ObjectNotFound:
		# unknown DeviceEUI =>add new tracker into database
		Tracker(dev_eui=dev_eui,
				device_name=device_name,
				score=0)
		commit()
		tracker = Tracker[dev_eui]

	try:
		cell = h3.geo_to_h3(lat=lat, lng=lng, resolution=cfg.H3_RESOLUTION)
		# # debugging one location
		# import math
		# if math.isclose(lat, 47.5442):
		# #if cell == '871f8e161ffffff':
		# 	# debugging
		# 	pass
	except TypeError:
		# without GPS-fix the trackers only send battery level without location
		return


	# implementation of game logic
	exploration = None
	try:
		# assumption: hexagon is already explored...
		exploration = Exploration[cell]
		# =>nothing to do
		return
	except pony.orm.core.ObjectNotFound:
		# unknown hexagon =>create new entry in database
		# =>need first to collect scores of surrounding hexes
		# (minimum is 1, we found a new hex)
		total_score = 1
		for neighbour in h3.hex_ring(cell, k=1):
			try:
				exploration = Exploration[neighbour]
				total_score += exploration.score
			except pony.orm.core.ObjectNotFound:
				# hexagon is not yet visited...
				pass

		# add new hexagon, update database
		Exploration(cell=cell,
					score=total_score,
					updated_at=updated_at
					)
		tracker.score += total_score
		commit()
		return


if __name__ == '__main__':
	pass

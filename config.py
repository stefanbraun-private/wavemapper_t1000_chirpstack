

# with help from https://github.com/sloria/environs

from environs import Env

env = Env()
env.read_env()  # read .env file, if it exists


DATABASE_FILENAME = env("DATABASE_FILENAME")

H3_RESOLUTION = env.int("H3_RESOLUTION")



# MQTT
MQTT = {}
with env.prefixed("MQTT_BROKER_"):
	MQTT["username"] = env("USERNAME")
	MQTT["password"] = env("PASSWORD")
	MQTT["host"] = env("HOST")
	MQTT["port"] = env.int("PORT")
	MQTT["enable_tls"] = env.bool("ENABLE_TLS")


# Folium map
MAP = {}
with env.prefixed("MAP_"):
	with env.prefixed("CENTER_"):
		MAP["latitude"] = env.float("LATITUDE")
		MAP["longitude"] = env.float("LONGITUDE")


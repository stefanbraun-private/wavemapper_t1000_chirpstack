from flask import Flask
import json
import paho.mqtt.client as mqtt
import h3
from threading import Lock
import config as cfg
import database as db
import datetime
import geojson
import folium


lock = Lock()

app = Flask(__name__)

@app.route("/")
def get_exploration_map():
    m = folium.Map(location=[cfg.MAP["latitude"], cfg.MAP["longitude"]])

    geojson_dict = generate_geojson()
    if geojson_dict:
        color_hex = 'red'

        nof_cells = 0
        with lock:
            nof_cells = len(db.get_explorations())

        style_function = lambda x: {'fillColor': x['properties']['fill'], 'color': x['properties']['stroke']}
        curr_name = "Wave-Mapping [{} cells]".format(nof_cells)
        folium.GeoJson(data=geojson_dict, name=curr_name, style_function=style_function).add_to(m)

    folium.LayerControl().add_to(m)

    # adding a legend with highscores
    # with help from https://www.geeksforgeeks.org/create-a-legend-on-a-folium-map-a-comprehensive-guide/
    trackers_lines = ''
    nof_trackers = 0
    for device_name, dev_eui, score in sorted(get_trackers(), key=lambda tracker: tracker[2], reverse=True):
        nof_trackers += 1
        trackers_lines += '         &nbsp; {} [{}]:   {} points &nbsp; <br>\n'.format(device_name, dev_eui, score)
    height = nof_trackers * 20 + 50
    legend_html = '''
    <div style="position: fixed; 
         bottom: 20px; left: 20px; width: 400px; height: {}px; 
         border:2px solid grey; z-index:9999; font-size:14px;
         background-color:white; opacity: 0.85;">
         &nbsp; <b>Highscore</b> <br>
         {}
    </div>
    '''.format(height, trackers_lines)

    # Add the legend to the map
    m.get_root().html.add_child(folium.Element(legend_html))


    # serving this HTML document in-memory without storing it as file
    # "exploration_backend" could do the whole process on one dedicated device (e.g. Raspberry Pi)
    # https://github.com/python-visualization/folium/issues/781#issuecomment-400930688
    #m.save(OUTPUT_FILENAME)
    #webbrowser.open(OUTPUT_FILENAME, new=2)  # open in new tab

    return m.get_root().render()



@app.route("/trackers")
def get_trackers():
    with lock:
        return db.get_trackers()


def generate_geojson():
    with lock:
        cells = db.get_explorations()
    if cells:
        # option: prepare visualisation: reduce resolution
        #cells = h3.compact(cells)
        # print('number of cells after "compact": {}'.format(len(cells)))


        # separate hexes by score
        total_score = 0
        for cell, score in cells:
            total_score += score
        avg_score = total_score / len(cells)
        #print("total_score={}, avg_score={}".format(total_score, avg_score))

        polygons_blue = []
        polygons_green = []
        polygons_red = []
        for cell, score in cells:
            polygon_set_of_sets = h3.h3_to_geo_boundary(h=cell, geo_json=True)
            if score == 1:
                # minimum score
                polygons_blue.append((list(polygon_set_of_sets),))
            elif score > avg_score:
                # maximum "height" of wave
                polygons_red.append((list(polygon_set_of_sets),))
            else:
                # wave has settled down
                polygons_green.append((list(polygon_set_of_sets),))

        feature_list = []
        for polygons, color in [(polygons_blue, "blue"),
                                (polygons_green, "green"),
                                (polygons_red, "red")]:
            multi_polygon = geojson.MultiPolygon(polygons)
            feature = geojson.Feature(geometry=multi_polygon, properties={'fill': color, 'stroke': color})
            feature_list.append(feature)
        feature_collection = geojson.FeatureCollection(feature_list)
        return feature_collection


@app.route("/geojson")
def get_geojson():
    return json.dumps(generate_geojson())


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with result code "+str(rc))

    # subscription for our own MQTT broker
    client.subscribe("uplinks/chirpstack/mappers/t1000/v0/json")

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.


# The callback for when a PUBLISH message is received from the MQTT broker.
def on_message(client, userdata, msg):
    #print(msg.topic+" "+str(msg.payload))

    #print("got MQTT message: topic={}, payload={}".format(msg.topic, msg.payload))

    if msg and msg.payload:
        # handle MQTT message
        payload_obj = json.loads(msg.payload)

        dev_eui = payload_obj["deviceInfo"]["devEui"]
        device_name = payload_obj["deviceInfo"].get("deviceName", "")

        # for debug and further analysis purposes of uplinks and RF conditions
        # (now we are sure payload is valid JSON)
        with open('uplink_debug_logfile.txt', 'a') as f:
            payload_json_str = json.dumps(payload_obj)
            f.write(''.join([payload_json_str, '\n']))

        # format in our own MQTT broker
        # https://docs.helium.com/use-the-network/console/integrations/json-schema/
        try:
            lat = payload_obj["object"]["latitude"]
            lon = payload_obj["object"]["longitude"]
        except Exception:
            # ignoring invalid location (perhaps device join message or device has no GPS fix?)
            lat, lon = 0, 0

        if lat and lon:
            # got a location (assumption: GPS tracker has a GPS-fix)
            # FIXME: insert validation of location, or limit game area

            print("add exploration: dev_eui={}, lat={}, lng={}".format(dev_eui, lat, lon))

            with lock:
                db.add_exploration(dev_eui=dev_eui,
                                   device_name=device_name,
                                   lat=lat,
                                   lng=lon,
                                   updated_at=datetime.datetime.utcnow())
        else:
            print("GPS tracker had uplink without valid GPS-data: dev_eui={}".format(dev_eui))


def setup_mqtt_client():

    # based on examples from https://pypi.org/project/paho-mqtt/
    mqttc = mqtt.Client()

    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    if cfg.MQTT["enable_tls"]:
        mqttc.tls_set()
    mqttc.username_pw_set(username=cfg.MQTT["username"], password=cfg.MQTT["password"])
    mqttc.connect(cfg.MQTT["host"], port=cfg.MQTT["port"])

    mqttc.loop_start()



if __name__ == '__main__':
    setup_mqtt_client()
    app.run()
